"""
Cross-Encoder Reranker Service.

Takes the top-N candidates from RRF fusion and rescores them with
BAAI/bge-reranker-base, returning only the top-M highest-scoring chunks.

Workflow
--------
    Top 20 RRF chunks
        ↓
    CrossEncoder.predict([(query, chunk_content), ...])
        ↓
    Sort by reranker score descending
        ↓
    Top 5 chunks

Features
--------
- Lazy model load (first call only)
- Async-friendly: inference runs in thread-pool executor
- Configurable candidate_count and final_count per-call or via settings
- Score logging for observability
- Graceful fallback: if the reranker fails the RRF order is preserved

Requires:
    pip install sentence-transformers
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from app.config.settings import RerankerSettings, settings
from app.schemas.rag import RetrievedChunkResult

logger = logging.getLogger("rag.reranker")


class RerankerError(Exception):
    """Raised when cross-encoder reranking fails."""


class RerankerService:
    """
    Cross-encoder reranker using BAAI/bge-reranker-base.

    Parameters
    ----------
    reranker_settings:
        Overrides for model name, candidate_count, final_count.
        Defaults to ``settings.reranker``.
    """

    def __init__(self, reranker_settings: RerankerSettings | None = None) -> None:
        self._cfg = reranker_settings or settings.reranker
        self._model: Any | None = None  # lazy-loaded CrossEncoder

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def rerank(
        self,
        query: str,
        candidates: list[RetrievedChunkResult],
        *,
        candidate_count: int | None = None,
        final_count: int | None = None,
    ) -> list[RetrievedChunkResult]:
        """
        Rerank *candidates* against *query* using the cross-encoder.

        Parameters
        ----------
        query:
            The original search / context query.
        candidates:
            Chunks to rerank (typically top-N from RRF).
        candidate_count:
            How many of the input candidates to actually score.
            Defaults to ``settings.reranker.candidate_count``.
        final_count:
            How many top-scoring chunks to return.
            Defaults to ``settings.reranker.final_count``.

        Returns
        -------
        list[RetrievedChunkResult]
            Top chunks re-ranked by cross-encoder score, tagged
            ``source="reranked"``.
        """
        if not candidates:
            return []

        resolved_candidates = candidate_count or self._cfg.candidate_count
        resolved_final = final_count or self._cfg.final_count

        # Slice to the candidate window
        pool = candidates[:resolved_candidates]

        try:
            t0 = time.perf_counter()

            scores = await self._score_pairs(query, pool)

            elapsed_ms = (time.perf_counter() - t0) * 1000

            # Log per-chunk scores for observability
            for chunk, score in zip(pool, scores):
                logger.debug(
                    "Reranker  chunk_id=%s  score=%.4f  rrf_rank=%d",
                    chunk.chunk_id,
                    score,
                    chunk.rank,
                )

            logger.info(
                "Reranker scored %d candidates in %.1f ms "
                "(max=%.4f, min=%.4f) → returning top %d.",
                len(pool),
                elapsed_ms,
                max(scores),
                min(scores),
                resolved_final,
            )

            # Sort by reranker score descending
            ranked = sorted(
                zip(scores, pool),
                key=lambda pair: pair[0],
                reverse=True,
            )

            top = ranked[:resolved_final]

            return [
                RetrievedChunkResult(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    project_id=chunk.project_id,
                    content=chunk.content,
                    section_title=chunk.section_title,
                    context_label=chunk.context_label,
                    score=float(score),
                    rank=new_rank,
                    source="reranked",
                    metadata={
                        **chunk.metadata,
                        "reranker_score": float(score),
                        "rrf_rank": chunk.rank,
                        "rrf_score": chunk.score,
                    },
                )
                for new_rank, (score, chunk) in enumerate(top, start=1)
            ]

        except RerankerError:
            raise
        except Exception as exc:
            logger.warning(
                "Reranker failed (%s); falling back to RRF order.", exc
            )
            # Graceful fallback: preserve RRF ranking, just relabel source
            fallback = candidates[:resolved_final]
            return [
                RetrievedChunkResult(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    project_id=c.project_id,
                    content=c.content,
                    section_title=c.section_title,
                    context_label=c.context_label,
                    score=c.score,
                    rank=i,
                    source="rrf_fallback",
                    metadata=c.metadata,
                )
                for i, c in enumerate(fallback, start=1)
            ]

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    async def _score_pairs(
        self,
        query: str,
        chunks: list[RetrievedChunkResult],
    ) -> list[float]:
        """Run cross-encoder inference in a thread-pool executor."""
        pairs = [(query, chunk.content) for chunk in chunks]
        scores: list[float] = await asyncio.get_running_loop().run_in_executor(
            None, self._predict_sync, pairs
        )
        return scores

    def _predict_sync(self, pairs: list[tuple[str, str]]) -> list[float]:
        """Synchronous cross-encoder prediction (called from executor)."""
        model = self._get_model()
        raw_scores = model.predict(pairs, show_progress_bar=False)
        # Convert numpy scalars to Python floats
        return [float(s) for s in raw_scores]

    def _get_model(self) -> Any:
        """Lazy-load the CrossEncoder model once."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RerankerError(
                    "sentence-transformers is required for reranking. "
                    "Install it with: pip install sentence-transformers"
                ) from exc

            logger.info("Loading reranker model: %s", self._cfg.model_name)
            t0 = time.perf_counter()
            self._model = CrossEncoder(self._cfg.model_name)
            logger.info(
                "Reranker model loaded in %.1f s.",
                time.perf_counter() - t0,
            )

        return self._model
