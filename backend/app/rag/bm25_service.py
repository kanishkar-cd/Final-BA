"""
BM25 Search Service.

Provides exact-match and keyword retrieval over document chunks using
PostgreSQL full-text search (tsvector / tsquery + GIN index).

Designed for queries like:
  - Requirement IDs: "FR-001", "NFR-002"
  - Technology terms:  "OAuth2", "API Gateway", "Session Timeout"
  - Free-text phrases: "user authentication login"

Requires:
    pip install asyncpg
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config.settings import RetrievalSettings, settings
from app.schemas.rag import RetrievedChunkResult

logger = logging.getLogger("rag.bm25")


class BM25Error(Exception):
    """Raised when a BM25 / FTS database operation fails."""


class BM25Service:
    """
    Full-text search over ``document_chunks`` via PostgreSQL tsvector.

    The asyncpg connection pool is created lazily on first use.

    Parameters
    ----------
    retrieval_settings:
        Contains ``postgres_dsn`` and ``bm25_top_k`` defaults.
    pool:
        Optional pre-existing asyncpg pool (useful for testing).
    """

    def __init__(
        self,
        retrieval_settings: RetrievalSettings | None = None,
        *,
        pool: Any | None = None,
    ) -> None:
        self._cfg = retrieval_settings or settings.retrieval
        self._pool: Any | None = pool

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
        Execute a full-text search and return ranked chunk results.

        The PostgreSQL ``ts_rank_cd`` function is used for scoring so that
        coverage and proximity are both considered.

        Parameters
        ----------
        query:
            Plain-text search string.  The DB-side ``rag_tsquery()`` helper
            function handles safe tsquery construction.
        top_k:
            Maximum results to return (defaults to ``settings.retrieval.bm25_top_k``).
        project_id / document_id / context_label:
            Optional scope filters.

        Returns
        -------
        list[RetrievedChunkResult]
            Ranked results with bm25 score and rank populated.
        """
        if not query or not query.strip():
            return []

        resolved_top_k = top_k or self._cfg.bm25_top_k

        pool = await self._get_pool()
        try:
            async with pool.acquire() as conn:
                t0 = time.perf_counter()
                rows = await self._execute_search(
                    conn,
                    query=query.strip(),
                    top_k=resolved_top_k,
                    project_id=project_id,
                    document_id=document_id,
                    context_label=context_label,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000

            logger.info(
                "BM25 search '%s' → %d results in %.1f ms.",
                query[:60],
                len(rows),
                elapsed_ms,
            )
            return self._rows_to_results(rows)

        except BM25Error:
            raise
        except Exception as exc:
            raise BM25Error(f"BM25 search failed: {exc}") from exc

    async def close(self) -> None:
        """Close the underlying connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    # ------------------------------------------------------------------ #
    # Query execution
    # ------------------------------------------------------------------ #

    # Base SELECT – all columns needed for RetrievedChunkResult
    _BASE_SELECT = """
        SELECT
            dc.id::text            AS chunk_id,
            dc.document_id::text,
            dc.project_id::text,
            dc.section_title,
            dc.context_label,
            dc.content,
            dc.token_count,
            dc.metadata            AS chunk_metadata,
            ts_rank_cd(dc.content_tsv, rag_tsquery($1), 32) AS bm25_score
        FROM   document_chunks dc
        WHERE  dc.deleted_at IS NULL
          AND  dc.content_tsv @@ rag_tsquery($1)
    """

    async def _execute_search(
        self,
        conn: Any,
        *,
        query: str,
        top_k: int,
        project_id: str | None,
        document_id: str | None,
        context_label: str | None,
    ) -> list[Any]:
        """Build the parameterised query and execute it."""
        sql_parts = [self._BASE_SELECT]
        params: list[Any] = [query]
        param_idx = 2  # $1 is already used for the query text

        if project_id:
            sql_parts.append(f"AND dc.project_id = ${param_idx}::uuid")
            params.append(project_id)
            param_idx += 1

        if document_id:
            sql_parts.append(f"AND dc.document_id = ${param_idx}::uuid")
            params.append(document_id)
            param_idx += 1

        if context_label:
            sql_parts.append(f"AND dc.context_label = ${param_idx}")
            params.append(context_label)
            param_idx += 1

        sql_parts.append(f"ORDER BY bm25_score DESC LIMIT ${param_idx}")
        params.append(top_k)

        sql = "\n".join(sql_parts)
        return await conn.fetch(sql, *params)

    # ------------------------------------------------------------------ #
    # Result mapping
    # ------------------------------------------------------------------ #

    @staticmethod
    def _rows_to_results(rows: list[Any]) -> list[RetrievedChunkResult]:
        results = []
        for rank, row in enumerate(rows, start=1):
            results.append(
                RetrievedChunkResult(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    project_id=row["project_id"],
                    content=row["content"],
                    section_title=row["section_title"] or "",
                    context_label=row["context_label"],
                    score=float(row["bm25_score"]),
                    rank=rank,
                    source="bm25",
                    metadata=dict(row["chunk_metadata"] or {}),
                )
            )
        return results

    # ------------------------------------------------------------------ #
    # Pool management
    # ------------------------------------------------------------------ #

    async def _get_pool(self) -> Any:
        if self._pool is None:
            try:
                import asyncpg
            except ImportError as exc:
                raise BM25Error(
                    "asyncpg is required for BM25 search. "
                    "Install it with: pip install asyncpg"
                ) from exc

            try:
                self._pool = await asyncpg.create_pool(
                    dsn=self._cfg.postgres_dsn,
                    min_size=2,
                    max_size=10,
                    command_timeout=30,
                )
                logger.info("asyncpg pool created for BM25 search.")
            except Exception as exc:
                raise BM25Error(
                    f"Failed to create asyncpg pool: {exc}"
                ) from exc

        return self._pool
