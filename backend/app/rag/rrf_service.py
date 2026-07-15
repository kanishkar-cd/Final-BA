"""
Reciprocal Rank Fusion (RRF) Service.

Merges two ranked lists (BM25 + Dense) into a single unified ranking.

RRF formula
-----------
    score(d) = Σ  1 / (k + rank_i(d))
              arms

where ``k`` is a smoothing constant (default 60, as in the original paper
by Cormack, Clarke & Buettcher, 2009).

Properties
----------
- Does not require score normalisation across arms
- Naturally handles missing entries (a document absent from one list
  simply does not accumulate that arm's contribution)
- Configurable ``rrf_k`` at service construction **and** per-call

Reference
---------
Cormack, G.V., Clarke, C.L.A., Buettcher, S. (2009).
"Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods."
SIGIR 2009.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from app.config.settings import settings
from app.schemas.rag import RetrievedChunkResult

logger = logging.getLogger("rag.rrf")


class RRFService:
    """
    Merge BM25 and dense ranked lists using Reciprocal Rank Fusion.

    Parameters
    ----------
    rrf_k:
        RRF smoothing constant.  Higher values compress rank differences
        (makes top-1 less dominant).  Default: ``settings.retrieval.rrf_k``.
    """

    def __init__(self, rrf_k: int | None = None) -> None:
        self._default_k = rrf_k or settings.retrieval.rrf_k

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def fuse(
        self,
        bm25_results: list[RetrievedChunkResult],
        dense_results: list[RetrievedChunkResult],
        *,
        rrf_k: int | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunkResult]:
        """
        Merge *bm25_results* and *dense_results* into a unified ranking.

        Parameters
        ----------
        bm25_results:
            Ranked list from the BM25 arm (rank already set).
        dense_results:
            Ranked list from the dense arm (rank already set).
        rrf_k:
            Per-call override for the RRF constant.
        top_k:
            Maximum number of fused results to return.  When ``None``
            all results are returned.

        Returns
        -------
        list[RetrievedChunkResult]
            Fused and re-ranked results tagged with ``source="rrf"``.
        """
        k = rrf_k if rrf_k is not None else self._default_k

        t0 = time.perf_counter()

        # chunk_id → running RRF score
        rrf_scores: dict[str, float] = defaultdict(float)
        # Preserve full result objects for payload retrieval
        chunk_payloads: dict[str, RetrievedChunkResult] = {}

        for result in bm25_results:
            rrf_scores[result.chunk_id] += 1.0 / (k + result.rank)
            chunk_payloads.setdefault(result.chunk_id, result)

        for result in dense_results:
            rrf_scores[result.chunk_id] += 1.0 / (k + result.rank)
            # Prefer dense payload (richer content field from Qdrant)
            chunk_payloads[result.chunk_id] = result

        # Sort by RRF score descending
        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)

        if top_k is not None:
            sorted_ids = sorted_ids[:top_k]

        fused: list[RetrievedChunkResult] = []
        for rank, chunk_id in enumerate(sorted_ids, start=1):
            payload = chunk_payloads[chunk_id]
            fused.append(
                RetrievedChunkResult(
                    chunk_id=payload.chunk_id,
                    document_id=payload.document_id,
                    project_id=payload.project_id,
                    content=payload.content,
                    section_title=payload.section_title,
                    context_label=payload.context_label,
                    score=rrf_scores[chunk_id],
                    rank=rank,
                    source="rrf",
                    metadata=payload.metadata,
                )
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "RRF fused %d BM25 + %d dense → %d results (k=%d) in %.2f ms.",
            len(bm25_results),
            len(dense_results),
            len(fused),
            k,
            elapsed_ms,
        )
        return fused

    def fuse_multi(
        self,
        ranked_lists: list[list[RetrievedChunkResult]],
        *,
        rrf_k: int | None = None,
        top_k: int | None = None,
    ) -> list[RetrievedChunkResult]:
        """
        General RRF fusion for N ranked lists.

        The two-list ``fuse()`` method is a convenience wrapper around this.
        """
        k = rrf_k if rrf_k is not None else self._default_k

        rrf_scores: dict[str, float] = defaultdict(float)
        chunk_payloads: dict[str, RetrievedChunkResult] = {}

        for ranked_list in ranked_lists:
            for result in ranked_list:
                rrf_scores[result.chunk_id] += 1.0 / (k + result.rank)
                chunk_payloads[result.chunk_id] = result

        sorted_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)
        if top_k is not None:
            sorted_ids = sorted_ids[:top_k]

        return [
            RetrievedChunkResult(
                chunk_id=chunk_payloads[cid].chunk_id,
                document_id=chunk_payloads[cid].document_id,
                project_id=chunk_payloads[cid].project_id,
                content=chunk_payloads[cid].content,
                section_title=chunk_payloads[cid].section_title,
                context_label=chunk_payloads[cid].context_label,
                score=rrf_scores[cid],
                rank=rank,
                source="rrf",
                metadata=chunk_payloads[cid].metadata,
            )
            for rank, cid in enumerate(sorted_ids, start=1)
        ]
