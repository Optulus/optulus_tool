from __future__ import annotations

from abc import ABC, abstractmethod
import hashlib
import math


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Local embeddings require sentence-transformers. "
                "Install with: pip install sentence-transformers"
            ) from exc
        self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed_text(self, text: str) -> list[float]:
        model = self._load_model()
        vector = model.encode(text, normalize_embeddings=True)
        return [float(value) for value in vector]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        model = self._load_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [[float(value) for value in vector] for vector in vectors]


class HashedEmbeddingProvider(EmbeddingProvider):
    """Deterministic local fallback mostly intended for tests."""

    def __init__(self, dimensions: int = 256) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self._dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        tokens = text.lower().split()
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self._dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) != len(right):
        raise ValueError("embedding vectors must have equal dimensions")
    return float(sum(l * r for l, r in zip(left, right)))
