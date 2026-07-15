"""
RAG Indexing Service.

Orchestrates the full embedding → vector-store → BM25-column pipeline
for a batch of document chunks.

Pipeline per chunk
------------------
1. Check if already indexed (skip unless ``reindex=True``)
2. Generate embedding via EmbeddingService (batched across all chunks)
3. Upsert embedding into Qdrant via VectorStoreService
4. Update ``context_label`` and ``embedding_indexed_at`` in PostgreSQL
   so BM25 search and the ``chunk_search_view`` stay consistent

The Postgres update (step 4) is lightweight – only two columns – and
does NOT regenerate the tsvector (that is maintained by the DB trigger
added in migration 005).

Observability
-------------
Logs embedding generation time, vector indexing time, and DB update time
separately so slow phases can be identified.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.config.settings import settings
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store_service import VectorStoreService
from app.schemas.rag import ChunkIndexInput, IndexResponse

logger = logging.getLogger("rag.indexing")


class IndexingError(Exception):
    """Raised when the indexing pipeline encounters an unrecoverable error."""


class IndexingService:
    """
    Coordinate embedding generation and vector storage for a batch of chunks.

    Parameters
    ----------
    embedding_service:
        Generates dense embeddings.
    vector_store:
        Persists embeddings in Qdrant.
    db_pool:
        Optional asyncpg pool for writing ``embedding_indexed_at`` back to
        PostgreSQL.  When ``None``, the DB-update step is skipped (useful
        for unit tests or environments without a live Postgres connection).
    """

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreService,
        *,
        db_pool: Any | None = None,
    ) -> None:
        self._embedder = embedding_service
        self._store = vector_store
        self._db_pool = db_pool

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def index_chunks(
        self,
        chunks: list[ChunkIndexInput],
        *,
        reindex: bool = False,
    ) -> IndexResponse:
        """
        Embed and index a batch of chunks.

        Parameters
        ----------
        chunks:
            Chunk inputs (content + metadata needed for the vector payload).
        reindex:
            When ``True``, re-embed and overwrite existing vectors.

        Returns
        -------
        IndexResponse
            Counts of indexed, skipped, and failed chunks.
        """
        if not chunks:
            return IndexResponse(
                indexed_count=0,
                skipped_count=0,
                failed_count=0,
                duration_ms=0.0,
            )

        wall_t0 = time.perf_counter()

        # Ensure the Qdrant collection exists before the first write
        await self._store.ensure_collection()

        to_index: list[ChunkIndexInput] = []
        skipped: list[str] = []

        if not reindex:
            # Check which chunks already have vectors in Qdrant
            for chunk in chunks:
                if await self._is_indexed(chunk.chunk_id):
                    skipped.append(chunk.chunk_id)
                else:
                    to_index.append(chunk)
        else:
            to_index = list(chunks)

        if skipped:
            logger.info("Skipping %d already-indexed chunks.", len(skipped))

        failed_ids: list[str] = []
        indexed_count = 0

        if to_index:
            indexed_count, failed_ids = await self._run_pipeline(to_index)

        wall_ms = (time.perf_counter() - wall_t0) * 1000
        logger.info(
            "Indexing complete: indexed=%d skipped=%d failed=%d in %.1f ms.",
            indexed_count,
            len(skipped),
            len(failed_ids),
            wall_ms,
        )

        return IndexResponse(
            indexed_count=indexed_count,
            skipped_count=len(skipped),
            failed_count=len(failed_ids),
            failed_chunk_ids=failed_ids,
            duration_ms=wall_ms,
        )

    # ------------------------------------------------------------------ #
    # Pipeline
    # ------------------------------------------------------------------ #

    async def _run_pipeline(
        self, chunks: list[ChunkIndexInput]
    ) -> tuple[int, list[str]]:
        """
        Run embed → upsert → db-update for all chunks in *chunks*.

        Returns (indexed_count, failed_chunk_ids).
        """
        # ── Step 1: Batch embedding ──────────────────────────────────────
        texts = [c.content for c in chunks]
        cache_keys = [c.chunk_id for c in chunks]  # use chunk_id as cache key

        t_embed = time.perf_counter()
        try:
            embeddings = await self._embedder.embed_texts(texts, cache_keys=cache_keys)
        except Exception as exc:
            logger.error("Batch embedding failed for all chunks: %s", exc)
            return 0, [c.chunk_id for c in chunks]

        embed_ms = (time.perf_counter() - t_embed) * 1000
        logger.info("Embedded %d chunks in %.1f ms.", len(chunks), embed_ms)

        # ── Step 2: Build Qdrant records ────────────────────────────────
        records: list[dict[str, Any]] = []
        failed_ids: list[str] = []

        for chunk, embedding in zip(chunks, embeddings):
            if embedding is None:
                logger.warning("No embedding returned for chunk_id=%s.", chunk.chunk_id)
                failed_ids.append(chunk.chunk_id)
                continue
            records.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "embedding": embedding,
                    "content": chunk.content,
                    "document_id": chunk.document_id,
                    "project_id": chunk.project_id,
                    "context_label": chunk.context_label,
                    "section_title": chunk.section_title,
                    "metadata": chunk.metadata,
                }
            )

        # ── Step 3: Batch upsert to Qdrant ──────────────────────────────
        if records:
            t_qdrant = time.perf_counter()
            try:
                await self._store.upsert_batch(records)
            except Exception as exc:
                logger.error("Qdrant upsert failed: %s", exc)
                failed_ids.extend(r["chunk_id"] for r in records)
                return 0, failed_ids

            qdrant_ms = (time.perf_counter() - t_qdrant) * 1000
            logger.info("Upserted %d vectors to Qdrant in %.1f ms.", len(records), qdrant_ms)

        # ── Step 4: Update postgres embedding_indexed_at ────────────────
        if records:
            t_pg = time.perf_counter()
            successfully_upserted = [r["chunk_id"] for r in records]
            pg_failed = await self._update_postgres_indexed_at(
                chunks=[c for c in chunks if c.chunk_id in set(successfully_upserted)],
            )
            failed_ids.extend(pg_failed)
            pg_ms = (time.perf_counter() - t_pg) * 1000
            logger.info("Updated PG embedding_indexed_at for %d chunks in %.1f ms.", len(successfully_upserted), pg_ms)

        indexed = len(records) - len([f for f in failed_ids if f in {r["chunk_id"] for r in records}])
        return max(indexed, 0), failed_ids

    async def _update_postgres_indexed_at(
        self, chunks: list[ChunkIndexInput]
    ) -> list[str]:
        """
        Set ``context_label`` and ``embedding_indexed_at = now()`` for each
        successfully indexed chunk.  Returns chunk_ids that failed the update.
        """
        failed: list[str] = []
        try:
            pool = await self._get_db_pool()
            async with pool.acquire() as conn:
                for chunk in chunks:
                    try:
                        await conn.execute(
                            """
                            UPDATE document_chunks
                               SET context_label        = $1,
                                   embedding_indexed_at = now()
                             WHERE id = $2::uuid
                               AND deleted_at IS NULL
                            """,
                            chunk.context_label,
                            chunk.chunk_id,
                        )
                    except Exception as exc:
                        logger.warning(
                            "PG update failed for chunk_id=%s: %s",
                            chunk.chunk_id,
                            exc,
                        )
                        failed.append(chunk.chunk_id)
        except Exception as exc:
            logger.error("PG pool acquire failed during indexing: %s", exc)
            failed.extend(c.chunk_id for c in chunks)
        return failed

    async def _get_db_pool(self) -> Any:
        if self._db_pool is None:
            import asyncpg
            from sqlalchemy.engine import make_url

            database_url = make_url(settings.retrieval.postgres_dsn)
            pool_kwargs: dict[str, Any] = {
                "host": database_url.host,
                "port": database_url.port or 5432,
                "user": database_url.username,
                "password": database_url.password,
                "database": database_url.database,
            }
            ssl_mode = database_url.query.get("ssl") or database_url.query.get("sslmode")
            if ssl_mode:
                pool_kwargs["ssl"] = ssl_mode

            self._db_pool = await asyncpg.create_pool(
                min_size=2,
                max_size=10,
                command_timeout=30,
                **pool_kwargs,
            )
        return self._db_pool

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    async def _is_indexed(self, chunk_id: str) -> bool:
        """
        Check whether a vector already exists in Qdrant for *chunk_id*.

        Uses a point-retrieval (no embedding needed) so it is fast.
        """
        try:
            client = await self._store._get_client()
            points = await client.retrieve(
                collection_name=self._store._cfg.collection_name,
                ids=[self._store._to_qdrant_id(chunk_id)],
                with_payload=False,
                with_vectors=False,
            )
            return len(points) > 0
        except Exception:
            # On any error assume not indexed so we proceed safely
            return False
