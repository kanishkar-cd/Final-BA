"""
Hybrid Retrieval Service.

Runs BM25 (sparse) and Dense (semantic) retrieval simultaneously and
returns both result sets.  The caller decides how to fuse them (RRF).

Input shape (mirrors Agent 2 output)
--------------------------------------
  epic            : "User Authentication"
  feature         : "Login"
  requirement_ids : ["FR-001", "FR-002"]

Query construction
------------------
  BM25 query  → requirement IDs joined with the epic/feature titles
  Dense query → "epic: <title> feature: <title> <req_ids>"
"""

from __future__ import annotations

import asyncio
import logging
import time

from app.rag.bm25_service import BM25Service
from app.rag.dense_retrieval_service import DenseRetrievalService
from app.schemas.rag import RetrievedChunkResult

logger = logging.getLogger("rag.hybrid_retrieval")


class HybridRetrievalResult:
    """Container for both retrieval arms before fusion."""

    __slots__ = ("bm25_results", "dense_results", "bm25_latency_ms", "dense_latency_ms")

    def __init__(
        self,
        bm25_results: list[RetrievedChunkResult],
        dense_results: list[RetrievedChunkResult],
        bm25_latency_ms: float,
        dense_latency_ms: float,
    ) -> None:
        self.bm25_results = bm25_results
        self.dense_results = dense_results
        self.bm25_latency_ms = bm25_latency_ms
        self.dense_latency_ms = dense_latency_ms


class HybridRetrievalService:
    """
    Execute BM25 and dense retrieval concurrently and return both result sets.

    Parameters
    ----------
    bm25_service:
        PostgreSQL full-text search service.
    dense_service:
        Qdrant cosine-similarity search service.
    """

    def __init__(
        self,
        bm25_service: BM25Service,
        dense_service: DenseRetrievalService,
    ) -> None:
        self._bm25 = bm25_service
        self._dense = dense_service

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def retrieve(
        self,
        *,
        epic: str,
        feature: str,
        requirement_ids: list[str] | None = None,
        project_id: str | None = None,
        document_id: str | None = None,
        bm25_top_k: int = 20,
        dense_top_k: int = 20,
    ) -> HybridRetrievalResult:
        """
        Run BM25 and dense search in parallel.

        Parameters
        ----------
        epic, feature:
            Planning artifact titles from Agent 2.
        requirement_ids:
            Requirement codes (e.g. "FR-001") to anchor BM25 keyword search.
        project_id / document_id:
            Optional scope filters passed through to both services.
        bm25_top_k / dense_top_k:
            Per-arm result limits.

        Returns
        -------
        HybridRetrievalResult
            Both result sets with per-arm latencies.
        """
        bm25_query = self._build_bm25_query(epic, feature, requirement_ids or [])
        dense_query = self._build_dense_query(epic, feature, requirement_ids or [])

        filters = {"project_id": project_id, "document_id": document_id}

        t0 = time.perf_counter()

        bm25_task = asyncio.create_task(
            self._timed_bm25(bm25_query, top_k=bm25_top_k, **filters)
        )
        dense_task = asyncio.create_task(
            self._timed_dense(dense_query, top_k=dense_top_k, **filters)
        )

        (bm25_results, bm25_ms), (dense_results, dense_ms) = await asyncio.gather(
            bm25_task, dense_task
        )

        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Hybrid retrieval for epic='%s' feature='%s': "
            "bm25=%d results (%.1fms), dense=%d results (%.1fms), total=%.1fms.",
            epic[:40],
            feature[:40],
            len(bm25_results),
            bm25_ms,
            len(dense_results),
            dense_ms,
            total_ms,
        )

        return HybridRetrievalResult(
            bm25_results=bm25_results,
            dense_results=dense_results,
            bm25_latency_ms=bm25_ms,
            dense_latency_ms=dense_ms,
        )

    async def retrieve_by_query(
        self,
        query: str,
        *,
        project_id: str | None = None,
        document_id: str | None = None,
        bm25_top_k: int = 20,
        dense_top_k: int = 20,
    ) -> HybridRetrievalResult:
        """
        Run hybrid retrieval for a free-text query (used by /api/rag/search).

        Both BM25 and dense use the same query string.
        """
        filters = {"project_id": project_id, "document_id": document_id}

        t0 = time.perf_counter()
        bm25_task = asyncio.create_task(
            self._timed_bm25(query, top_k=bm25_top_k, **filters)
        )
        dense_task = asyncio.create_task(
            self._timed_dense(query, top_k=dense_top_k, **filters)
        )

        (bm25_results, bm25_ms), (dense_results, dense_ms) = await asyncio.gather(
            bm25_task, dense_task
        )
        total_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "Hybrid search '%s' bm25=%d/%.1fms dense=%d/%.1fms total=%.1fms.",
            query[:60],
            len(bm25_results),
            bm25_ms,
            len(dense_results),
            dense_ms,
            total_ms,
        )
        return HybridRetrievalResult(
            bm25_results=bm25_results,
            dense_results=dense_results,
            bm25_latency_ms=bm25_ms,
            dense_latency_ms=dense_ms,
        )

    # ------------------------------------------------------------------ #
    # Query construction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _build_bm25_query(
        epic: str, feature: str, requirement_ids: list[str]
    ) -> str:
        """
        Keyword-weighted query optimised for PostgreSQL FTS.

        Requirement IDs are placed first because they are high-precision
        anchors.  The epic/feature titles provide broader context.
        """
        parts: list[str] = []
        parts.extend(requirement_ids)
        if feature:
            parts.append(feature)
        if epic:
            parts.append(epic)
        return " ".join(parts)

    @staticmethod
    def _build_dense_query(
        epic: str, feature: str, requirement_ids: list[str]
    ) -> str:
        """
        Semantic query for the embedding model.

        Structured sentence improves BGE retrieval quality.
        """
        req_str = ", ".join(requirement_ids) if requirement_ids else ""
        parts = [f"Epic: {epic}", f"Feature: {feature}"]
        if req_str:
            parts.append(f"Requirements: {req_str}")
        return ". ".join(parts)

    # ------------------------------------------------------------------ #
    # Timed wrappers
    # ------------------------------------------------------------------ #

    async def _timed_bm25(
        self,
        query: str,
        *,
        top_k: int,
        project_id: str | None,
        document_id: str | None,
    ) -> tuple[list[RetrievedChunkResult], float]:
        t0 = time.perf_counter()
        try:
            results = await self._bm25.search(
                query,
                top_k=top_k,
                project_id=project_id,
                document_id=document_id,
            )
        except Exception as exc:
            logger.warning("BM25 arm failed: %s", exc)
            results = []
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return results, elapsed_ms

    async def _timed_dense(
        self,
        query: str,
        *,
        top_k: int,
        project_id: str | None,
        document_id: str | None,
    ) -> tuple[list[RetrievedChunkResult], float]:
        t0 = time.perf_counter()
        try:
            results = await self._dense.search(
                query,
                top_k=top_k,
                project_id=project_id,
                document_id=document_id,
            )
        except Exception as exc:
            logger.warning("Dense arm failed: %s", exc)
            results = []
        elapsed_ms = (time.perf_counter() - t0) * 1000
        return results, elapsed_ms
