"""
Dense Retrieval Service.

Semantic retrieval: encode a query with the embedding model, then
run cosine similarity search in Qdrant.

Query flow
----------
User Query → EmbeddingService.embed_single() → VectorStoreService.search()
           → top_k results with cosine scores

Supports
--------
- Configurable top_k per call
- project_id / document_id / context_label metadata filtering
- Latency logging
"""

from __future__ import annotations

import logging
import time

from app.config.settings import RetrievalSettings, settings
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store_service import VectorStoreService
from app.schemas.rag import RetrievedChunkResult

logger = logging.getLogger("rag.dense_retrieval")


class DenseRetrievalError(Exception):
    """Raised when dense retrieval fails."""


class DenseRetrievalService:
    """
    Semantic retrieval via query embedding + Qdrant similarity search.

    Parameters
    ----------
    embedding_service:
        Used to embed the search query at query time.
    vector_store:
        Used to execute the ANN search against Qdrant.
    retrieval_settings:
        Provides the default ``dense_top_k``.
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreService,
        retrieval_settings: RetrievalSettings | None = None,
    ) -> None:
        self._embedder = embedding_service
        self._store = vector_store
        self._cfg = retrieval_settings or settings.retrieval

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        project_id: str | None = None,
        document_id: str | None = None,
        context_label: str | None = None,
    ) -> list[RetrievedChunkResult]:
        """
        Embed *query* and return the most semantically similar chunks.

        Parameters
        ----------
        query:
            Natural-language query (e.g. "User Authentication Login").
        top_k:
            Number of results to return.  Defaults to
            ``settings.retrieval.dense_top_k``.
        project_id / document_id / context_label:
            Payload filters applied inside Qdrant before ranking.

        Returns
        -------
        list[RetrievedChunkResult]
            Cosine-scored results tagged with ``source="dense"``.
        """
        if not query or not query.strip():
            return []

        resolved_top_k = top_k or self._cfg.dense_top_k

        try:
            t0 = time.perf_counter()

            # Embed the query using BGE's query prefix for asymmetric retrieval
            query_vector = await self._embed_query(query.strip())

            # ANN search in Qdrant
            raw_results = await self._store.search(
                query_vector,
                top_k=resolved_top_k,
                project_id=project_id,
                document_id=document_id,
                context_label=context_label,
            )

            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "Dense retrieval '%s' → %d results in %.1f ms.",
                query[:60],
                len(raw_results),
                elapsed_ms,
            )

            return self._to_results(raw_results)

        except Exception as exc:
            raise DenseRetrievalError(
                f"Dense retrieval failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    async def _embed_query(self, query: str) -> list[float]:
        """
        Embed a query string.

        BGE models use a dedicated query instruction for asymmetric retrieval:
        the passage prefix is applied in EmbeddingService._encode_sync(),
        so here we wrap the text with the query-side instruction before handing
        it to the service.
        """
        # BGE query prefix (distinct from the passage prefix used at index time)
        prefixed = f"Represent this sentence for searching relevant passages: {query}"
        # We bypass the cache prefix logic by calling embed_texts directly;
        # query embeddings are not cached (they change every request).
        vectors = await self._embedder.embed_texts([prefixed])
        return vectors[0]

    @staticmethod
    def _to_results(raw: list[dict]) -> list[RetrievedChunkResult]:
        results = []
        for rank, item in enumerate(raw, start=1):
            results.append(
                RetrievedChunkResult(
                    chunk_id=item["chunk_id"],
                    document_id=item["document_id"],
                    project_id=item["project_id"],
                    content=item.get("content", ""),
                    section_title=item.get("section_title", ""),
                    context_label=item.get("context_label"),
                    score=item["score"],
                    rank=rank,
                    source="dense",
                    metadata=item.get("metadata", {}),
                )
            )
        return results
