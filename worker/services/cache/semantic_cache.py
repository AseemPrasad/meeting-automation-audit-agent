"""Redis vector semantic cache.

Caches previously generated transcript analyses so that duplicate or highly
similar transcript segments can be served from the cache without invoking the
LLM again. Uses RedisVL vector search over embeddings produced by a
``VectorProvider``.

Key behaviors:
- lookup(text, threshold=0.95): KNN cosine-similarity search; returns the
  cached JSON payload when the top hit >= threshold.
- store(text, payload, ttl_seconds): embeds and upserts the vector entry.
- purge(tenant_id=None): manual cache eviction (all or per-tenant).
- Per-tenant isolation via a ``tenant_id`` field on every entry.
"""

import json
import logging
import os
import time
import uuid
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from worker.services.embeddings.vector_provider import (
    VectorProvider,
    build_embedding_provider,
)

load_dotenv()

logger = logging.getLogger(__name__)

# Default cosine-similarity threshold required to serve a cached response.
DEFAULT_SIMILARITY_THRESHOLD = 0.95
# Default TTL for cached entries (seconds). 0 / None disables expiry.
DEFAULT_TTL_SECONDS = 86400  # 24h


class SemanticCacheError(Exception):
    """Raised for cache infrastructure failures (Redis/index problems)."""


class SemanticCache:
    """Vector semantic cache backed by RedisVL."""

    INDEX_NAME = "semantic_cache_idx"

    def __init__(
        self,
        provider: Optional[VectorProvider] = None,
        redis_url: Optional[str] = None,
        index_name: str = INDEX_NAME,
        threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        default_ttl: int = DEFAULT_TTL_SECONDS,
        store: Any = None,  # injected in-memory store for tests
    ) -> None:
        """Initialize the cache. If ``store`` is injected, no Redis is used."""
        self.provider = provider or build_embedding_provider()
        self.redis_url = redis_url or os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self.index_name = index_name
        self.threshold = float(
            os.getenv("SEMANTIC_CACHE_THRESHOLD", str(threshold))
        )
        self.default_ttl = int(
            os.getenv("SEMANTIC_CACHE_TTL", str(default_ttl))
        )
        self._store = store
        if store is None:
            self._init_redis()
        else:
            self._search = None  # in-memory path below

    # ------------------------------------------------------------------
    # Redis setup
    # ------------------------------------------------------------------
    def _init_redis(self) -> None:
        """Create the Redis client and ensure the vector index exists."""
        try:
            import redis
            from redisvl.index import SearchIndex
            from redisvl.utils.vectorize import CustomVectorizer
        except ImportError as exc:  # pragma: no cover - guard
            raise SemanticCacheError(
                "redisvl / redis are not installed. "
                "Run: pip install redisvl redis"
            ) from exc

        self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
        self._redis.ping()

        # Schema for the vector index. The `vector` field is a float32 array
        # with a cosine (IP) distance metric and the configured dimensions.
        self._vectorizer = CustomVectorizer(self.provider.embed)
        self._index = SearchIndex.from_dict(
            {
                "index": {"name": self.index_name, "prefix": "semcache"},
                "fields": [
                    {"name": "payload", "type": "TEXT"},
                    {"name": "tenant_id", "type": "TAG"},
                    {
                        "name": "vector",
                        "type": "VECTOR",
                        "attrs": {
                            "algorithm": "FLAT",
                            "datatype": "FLOAT32",
                            "dimension": self.provider.dimensions,
                            "distance_metric": "COSINE",
                        },
                    },
                ],
            },
            redis_client=self._redis,
            vectorizer=self._vectorizer,
        )
        try:
            self._index.create(overwrite=False)
        except Exception as exc:  # pragma: no cover - index may already exist
            logger.debug("Index creation skipped: %s", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def lookup(
        self,
        text: str,
        tenant_id: str = "default",
        threshold: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Search for a cached analysis semantically similar to ``text``.

        Returns the stored payload dict when the top result's cosine
        similarity is >= threshold, otherwise None.
        """
        if not text or not text.strip():
            return None

        if self._store is not None:
            return self._lookup_in_memory(text, tenant_id, threshold)

        return self._lookup_redis(text, tenant_id, threshold)

    def store(
        self,
        text: str,
        payload: Dict[str, Any],
        tenant_id: str = "default",
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Embed and upsert ``payload`` for ``text`` under ``tenant_id``."""
        if not text or not text.strip():
            raise SemanticCacheError("Cannot cache empty text")

        ttl = self.default_ttl if ttl_seconds is None else ttl_seconds
        key = f"semcache:{tenant_id}:{uuid.uuid4().hex}"

        if self._store is not None:
            self._store_text(text, payload, tenant_id, ttl, key)
            return

        self._store_redis(text, payload, tenant_id, ttl, key)

    def purge(self, tenant_id: Optional[str] = None) -> int:
        """Manually evict cache entries.

        Args:
            tenant_id: when given, only that tenant's entries are removed;
                otherwise the whole cache is purged.
        Returns:
            Number of keys removed.
        """
        if self._store is not None:
            return self._purge_in_memory(tenant_id)

        return self._purge_redis(tenant_id)

    def close(self) -> None:
        """Release the underlying Redis connection (no-op for in-memory)."""
        if getattr(self, "_redis", None) is not None:
            try:
                self._redis.close()
            except Exception:  # pragma: no cover - best effort
                pass

    def flush(self) -> None:
        """Alias for purge() that clears everything."""
        self.purge()

    # ------------------------------------------------------------------
    # In-memory implementation (used by tests)
    # ------------------------------------------------------------------
    def _lookup_in_memory(
        self, text: str, tenant_id: str, threshold: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        thr = self.threshold if threshold is None else threshold
        query = self.provider.embed(text)
        best_score, best_payload = -1.0, None
        now = time.time()
        for entry in self._store["entries"]:
            if entry["tenant_id"] != tenant_id:
                continue
            if entry["expires_at"] is not None and entry["expires_at"] < now:
                continue
            score = _cosine_similarity(query, entry["vector"])
            if score > best_score:
                best_score = score
                best_payload = entry["payload"]
        if best_score >= thr and best_payload is not None:
            return json.loads(best_payload)
        return None

    def _store_text(
        self,
        text: str,
        payload: Dict[str, Any],
        tenant_id: str,
        ttl: int,
        key: str,
    ) -> None:
        self._store["entries"].append(
            {
                "key": key,
                "tenant_id": tenant_id,
                "text": text,
                "vector": self.provider.embed(text),
                "payload": json.dumps(payload),
                "expires_at": (time.time() + ttl) if ttl else None,
            }
        )

    def _purge_in_memory(self, tenant_id: Optional[str]) -> int:
        remaining = []
        removed = 0
        for entry in self._store["entries"]:
            if tenant_id is None or entry["tenant_id"] == tenant_id:
                removed += 1
            else:
                remaining.append(entry)
        self._store["entries"] = remaining
        return removed

    # ------------------------------------------------------------------
    # Redis implementation
    # ------------------------------------------------------------------
    def _lookup_redis(
        self, text: str, tenant_id: str, threshold: Optional[float]
    ) -> Optional[Dict[str, Any]]:
        thr = self.threshold if threshold is None else threshold
        try:
            results = self._index.query(
                text,
                return_fields=["payload", "tenant_id", "vector_distance"],
                num_results=1,
                filters={"tenant_id": tenant_id},
            )
            if not results:
                return None
            top = results[0]
            distance = float(top.get("vector_distance", 1.0))
            # Redis COSINE distance is 1 - cosine_similarity.
            similarity = 1.0 - distance
            if similarity >= thr:
                return json.loads(top["payload"])
            return None
        except Exception as exc:  # pragma: no cover - infra failures
            logger.warning("Semantic cache lookup failed: %s", exc)
            return None

    def _store_redis(
        self,
        text: str,
        payload: Dict[str, Any],
        tenant_id: str,
        ttl: int,
        key: str,
    ) -> None:
        self._index.load(
            [
                {
                    "id": key,
                    "text": text,
                    "payload": json.dumps(payload),
                    "tenant_id": tenant_id,
                    "metadata": {"created_at": time.time()},
                }
            ],
            ttl=ttl if ttl else None,
        )

    def _purge_redis(self, tenant_id: Optional[str]) -> int:
        try:
            if tenant_id is None:
                self._index.clear()
                return -1  # unknown count on full clear
            # TAG filter delete is not atomic in redisvl; drop matching keys.
            keys = list(self._redis.scan_iter(f"semcache:{tenant_id}:*"))
            if keys:
                self._redis.delete(*keys)
            return len(keys)
        except Exception as exc:  # pragma: no cover
            logger.warning("Semantic cache purge failed: %s", exc)
            return 0


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length float vectors."""
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

