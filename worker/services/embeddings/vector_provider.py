"""Lightweight embedding provider abstraction.

Two backends are supported:
- "local":  all-MiniLM-L6-v2 via sentence-transformers (offline, no API cost)
- "openai": text-embedding-3-small via the OpenAI SDK

The backend is selected with the EMBEDDING_PROVIDER environment variable
(defaults to "local" so no network or API key is required).
"""

import os
from abc import ABC, abstractmethod
from typing import List

from dotenv import load_dotenv

load_dotenv()


class EmbeddingError(Exception):
    """Raised when a vector cannot be produced by the configured backend."""


class VectorProvider(ABC):
    """Interface for producing text embeddings."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier (e.g. "all-MiniLM-L6-v2", "text-embedding-3-small")."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Return the embedding vector for a single text."""

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Return embeddings for a batch of texts (default: one-by-one)."""
        return [self.embed(t) for t in texts]

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimensionality (used to build the Redis index schema)."""


class LocalMiniLMProvider(VectorProvider):
    """all-MiniLM-L6-v2 via sentence-transformers (offline)."""

    _MODEL_NAME = "all-MiniLM-L6-v2"
    _DIMENSIONS = 384

    def __init__(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - import guard
            raise EmbeddingError(
                "sentence-transformers is not installed. "
                "Run: pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(self._MODEL_NAME)

    @property
    def name(self) -> str:
        return self._MODEL_NAME

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS

    def embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")
        vector = self._model.encode(text, normalize_embeddings=True)
        return [float(v) for v in vector]


class OpenAIEmbeddingProvider(VectorProvider):
    """text-embedding-3-small via the OpenAI SDK."""

    _MODEL_NAME = "text-embedding-3-small"
    _DIMENSIONS = 1536

    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EmbeddingError(
                "OPENAI_API_KEY is required when EMBEDDING_PROVIDER=openai"
            )
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)

    @property
    def name(self) -> str:
        return self._MODEL_NAME

    @property
    def dimensions(self) -> int:
        return self._DIMENSIONS

    def embed(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")
        response = self._client.embeddings.create(
            model=self._MODEL_NAME, input=text
        )
        return [float(v) for v in response.data[0].embedding]


def build_embedding_provider() -> VectorProvider:
    """Instantiate the embedding provider selected by EMBEDDING_PROVIDER."""
    provider_name = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower()
    if provider_name == "openai":
        return OpenAIEmbeddingProvider()
    if provider_name == "local":
        return LocalMiniLMProvider()
    raise EmbeddingError(
        f"Unknown EMBEDDING_PROVIDER '{provider_name}'. "
        "Use 'local' or 'openai'."
    )

