"""Tests for the Redis vector semantic cache.

These use a deterministic fake embedding provider and the in-memory store path,
so no Redis server, redisvl, or sentence-transformers are required.
"""

import math

import pytest

from worker.services.cache.semantic_cache import SemanticCache
from worker.services.embeddings.vector_provider import VectorProvider


class _FakeProvider(VectorProvider):
    """Deterministic embeddings: a simple bag-of-words float vector.

    Each token in the message maps to a fixed dimension so that similar
    sentences share dimensions and get high cosine similarity.
    """

    def __init__(self, dim=384):
        self._dim = dim
        self._token_to_idx = {}

    @property
    def name(self):
        return "fake-provider"

    @property
    def dimensions(self):
        return self._dim

    def _tokens(self, text):
        return text.lower().replace(".", " ").split()

    def embed(self, text):
        vec = [0.0] * self._dim
        for token in self._tokens(text):
            idx = self._token_to_idx.setdefault(token, len(self._token_to_idx))
            if idx < self._dim:
                vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec


def _make_cache(**kwargs):
    provider = _FakeProvider()
    return SemanticCache(
        provider=provider,
        store={"entries": []},
        threshold=kwargs.pop("threshold", 0.95),
        **kwargs,
    )


def test_lookup_miss_on_empty_cache():
    cache = _make_cache()
    assert cache.lookup("hello world") is None


def test_store_then_exact_lookup_hit():
    cache = _make_cache()
    payload = {"summary": "s", "tasks": ["t1"], "decisions": ["d1"]}
    cache.store("Alice will send the quarterly report", payload)
    result = cache.lookup("Alice will send the quarterly report")
    assert result == payload


def test_tenant_isolation():
    cache = _make_cache()
    payload = {"summary": "tenant A"}
    cache.store("shared content", payload, tenant_id="tenant-a")
    # Same text, different tenant -> miss.
    assert cache.lookup("shared content", tenant_id="tenant-b") is None
    # Same tenant -> hit.
    assert cache.lookup("shared content", tenant_id="tenant-a") == payload


def test_purge_by_tenant():
    cache = _make_cache()
    cache.store("text a", {"summary": "a"}, tenant_id="t1")
    cache.store("text b", {"summary": "b"}, tenant_id="t2")
    removed = cache.purge(tenant_id="t1")
    assert removed == 1
    assert cache.lookup("text a", tenant_id="t1") is None
    # t2 unaffected.
    assert cache.lookup("text b", tenant_id="t2") == {"summary": "b"}


def test_purge_all():
    cache = _make_cache()
    cache.store("text a", {"summary": "a"}, tenant_id="t1")
    cache.store("text b", {"summary": "b"}, tenant_id="t2")
    removed = cache.purge()
    assert removed == 2
    assert cache.lookup("text a", tenant_id="t1") is None
    assert cache.lookup("text b", tenant_id="t2") is None


def test_ttl_expiry():
    cache = _make_cache()
    cache.store("data", {"summary": "s"}, ttl_seconds=0)  # 0 => no expiry set
    # force expiry by setting a past expires_at
    cache._store["entries"][0]["expires_at"] = 0
    assert cache.lookup("data") is None


def test_lookup_rejects_empty_text():
    cache = _make_cache()
    assert cache.lookup("") is None
    assert cache.lookup("   ") is None

