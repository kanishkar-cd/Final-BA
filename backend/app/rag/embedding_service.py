"""
Embedding Generation Service.

Generates dense vector embeddings for document chunks using
BAAI/bge-base-en-v1.5 (768-dimensional).

Features
--------
- Lazy model loading (loaded once, reused across calls)
- Batch embedding with configurable batch size
- Async-friendly: CPU-bound encoding runs in a thread pool executor
- Redis caching of embeddings keyed by content hash
- Configurable retry on transient failures
- Structured latency logging
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Sequence

from app.config.settings import EmbeddingSettings, settings

logger = logging.getLogger("rag.embedding")


class EmbeddingError(Exception):
    """Raised when embedding generation fails after retries."""


class EmbeddingService:
    """
    Generate and optionally cache chunk embeddings.

    Parameters
    ----------
    embedding_settings:
        Configuration overrides. Defaults to ``settings.embedding``.
    redis_client:
        Optional async Redis client used for embedding caching.
        When ``None``, caching is disabled regardless of settings.
    """

    def __init__(
        self,
        *,
        embedding_settings: EmbeddingSettings | None = None,
        redis_client: Any | None = None,
    ) -> None:
        self._cfg = embedding_settings or settings.embedding
        self._redis = redis_client
        self._model: Any | None = None  # lazy-loaded SentenceTransformer

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def embed_texts(
        self,
        texts: Sequence[str],
        *,
        cache_keys: Sequence[str] | None = None,
    ) -> list[list[float]]:
        """
        Return one embedding vector per input text.

        Parameters
        ----------
        texts:
            Strings to embed.
        cache_keys:
            Optional per-text cache identifiers (e.g. content hashes).
            Must have the same length as *texts* when supplied.

        Returns
        -------
        list[list[float]]
            Embedding vectors in the same order as *texts*.
        """
        if not texts:
            return []

        texts = list(texts)

        if cache_keys is not None and len(cache_keys) != len(texts):
            raise ValueError("cache_keys must have the same length as texts")

        # 1. Attempt cache hits when Redis is available
        results: list[list[float] | None] = [None] * len(texts)
        uncached_indices: list[int] = []

        if self._redis is not None and self._cfg.cache_enabled and cache_keys:
            for idx, key in enumerate(cache_keys):
                cached = await self._get_cached_embedding(key)
                if cached is not None:
                    results[idx] = cached
                else:
                    uncached_indices.append(idx)
        else:
            uncached_indices = list(range(len(texts)))

        if not uncached_indices:
            return results  # type: ignore[return-value]

        # 2. Encode uncached texts in batches
        uncached_texts = [texts[i] for i in uncached_indices]
        vectors = await self._encode_with_retry(uncached_texts)

        # 3. Populate results and write-through to cache
        for list_pos, original_idx in enumerate(uncached_indices):
            vec = vectors[list_pos]
            results[original_idx] = vec
            if self._redis is not None and self._cfg.cache_enabled and cache_keys:
                await self._set_cached_embedding(cache_keys[original_idx], vec)

        return results  # type: ignore[return-value]

    async def embed_single(self, text: str, *, cache_key: str | None = None) -> list[float]:
        """Convenience wrapper for a single text."""
        vectors = await self.embed_texts([text], cache_keys=[cache_key] if cache_key else None)
        return vectors[0]

    @property
    def vector_size(self) -> int:
        """Return the dimensionality of the embedding model's output."""
        return settings.qdrant.vector_size

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _encode_with_retry(self, texts: list[str]) -> list[list[float]]:
        """Encode *texts* with exponential-backoff retries on failure."""
        last_exc: Exception | None = None
        delay = self._cfg.retry_delay_seconds

        for attempt in range(1, self._cfg.max_retries + 1):
            try:
                t0 = time.perf_counter()
                vectors = await self._encode_batched(texts)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "Embedded %d texts in %.1f ms (attempt %d)",
                    len(texts),
                    elapsed_ms,
                    attempt,
                )
                return vectors
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Embedding attempt %d/%d failed: %s",
                    attempt,
                    self._cfg.max_retries,
                    exc,
                )
                if attempt < self._cfg.max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2  # exponential back-off

        raise EmbeddingError(
            f"Embedding failed after {self._cfg.max_retries} attempts."
        ) from last_exc

    async def _encode_batched(self, texts: list[str]) -> list[list[float]]:
        """Split *texts* into batches and encode via the thread pool."""
        all_vectors: list[list[float]] = []
        batch_size = self._cfg.batch_size

        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            vectors = await asyncio.get_running_loop().run_in_executor(
                None, self._encode_sync, batch
            )
            all_vectors.extend(vectors)

        return all_vectors

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous encoding on the calling thread (runs in executor)."""
        model = self._get_model()
        # BGE models need a query prefix for asymmetric retrieval.
        # For document-side encoding we use the passage prefix per BGE docs.
        prefixed = [f"Represent this passage: {t}" for t in texts]
        raw = model.encode(
            prefixed,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [vec.tolist() for vec in raw]

    def _get_model(self) -> Any:
        """Lazy-load and cache the SentenceTransformer model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise EmbeddingError(
                    "sentence-transformers is required for embedding generation. "
                    "Install it with: pip install sentence-transformers"
                ) from exc

            logger.info("Loading embedding model: %s", self._cfg.model_name)
            self._model = SentenceTransformer(self._cfg.model_name)
            logger.info("Embedding model loaded (vector_size=%d).", self.vector_size)

        return self._model

    # ------------------------------------------------------------------ #
    # Redis cache helpers
    # ------------------------------------------------------------------ #

    _CACHE_PREFIX = "rag:embedding:"
    _CACHE_TTL = 60 * 60 * 24 * 30  # 30 days

    async def _get_cached_embedding(self, cache_key: str) -> list[float] | None:
        import json

        try:
            raw = await self._redis.get(f"{self._CACHE_PREFIX}{cache_key}")
            if raw is not None:
                return json.loads(raw)
        except Exception as exc:
            logger.debug("Cache read failed for %s: %s", cache_key, exc)
        return None

    async def _set_cached_embedding(
        self, cache_key: str, vector: list[float]
    ) -> None:
        import json

        try:
            await self._redis.set(
                f"{self._CACHE_PREFIX}{cache_key}",
                json.dumps(vector),
                ex=self._CACHE_TTL,
            )
        except Exception as exc:
            logger.debug("Cache write failed for %s: %s", cache_key, exc)
