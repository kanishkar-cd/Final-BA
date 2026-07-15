"""
Qdrant Vector Store Service.

Manages the ``brd_chunks`` collection in Qdrant:
  - Auto-creates the collection on first use
  - Upsert embeddings with chunk/document/project payload
  - Delete vectors by chunk_id or by document_id / project_id filter
  - Similarity search with optional metadata filters
  - Re-index support (delete + upsert)
  - Batch insertion

Requires:
    pip install qdrant-client
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from app.config.settings import QdrantSettings, settings

logger = logging.getLogger("rag.vector_store")

# Qdrant local mode stores data on the client instance. Share that instance so
# independently constructed RAG services see the same local collections.
_shared_local_client: Any | None = None


class VectorStoreError(Exception):
    """Raised when a Qdrant operation fails."""


class VectorStoreService:
    """
    Thin async wrapper around the Qdrant Python client.

    The client is created lazily on first use so the service can be
    instantiated at import time without requiring a live Qdrant instance.
    """

    def __init__(self, qdrant_settings: QdrantSettings | None = None) -> None:
        self._cfg = qdrant_settings or settings.qdrant
        self._client: Any | None = None

    # ------------------------------------------------------------------ #
    # Collection management
    # ------------------------------------------------------------------ #

    async def ensure_collection(self) -> None:
        """Create or recreate the collection if it does not exist or has mismatched dimensions."""
        client = await self._get_client()
        try:
            from qdrant_client.http.models import Distance, VectorParams

            existing = await client.get_collections()
            names = {c.name for c in existing.collections}
            
            recreate = False
            if self._cfg.collection_name in names:
                try:
                    info = await client.get_collection(self._cfg.collection_name)
                    vectors_config = info.config.params.vectors
                    current_size = None
                    if hasattr(vectors_config, "size"):
                        current_size = vectors_config.size
                    elif isinstance(vectors_config, dict) and "size" in vectors_config:
                        current_size = vectors_config["size"]
                    
                    if current_size is not None and current_size != self._cfg.vector_size:
                        logger.warning(
                            "Collection '%s' has mismatched vector dimension %d (expected %d). Recreating...",
                            self._cfg.collection_name,
                            current_size,
                            self._cfg.vector_size,
                        )
                        await client.delete_collection(self._cfg.collection_name)
                        recreate = True
                except Exception as exc:
                    logger.warning("Failed to check collection info: %s. Proceeding assuming no recreation needed.", exc)

            if self._cfg.collection_name not in names or recreate:
                await client.create_collection(
                    collection_name=self._cfg.collection_name,
                    vectors_config=VectorParams(
                        size=self._cfg.vector_size,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(
                    "Created Qdrant collection '%s' (size=%d, distance=COSINE).",
                    self._cfg.collection_name,
                    self._cfg.vector_size,
                )
            else:
                logger.debug(
                    "Qdrant collection '%s' already exists.", self._cfg.collection_name
                )
        except Exception as exc:
            endpoint = self._endpoint_description()
            guidance = (
                " Start Qdrant before indexing, or configure QDRANT_HOST and "
                "QDRANT_PORT for a reachable Qdrant server. When the backend "
                "runs in Docker Compose, QDRANT_HOST must be 'qdrant', not "
                "'localhost'."
            )
            raise VectorStoreError(
                f"Failed to ensure Qdrant collection '{self._cfg.collection_name}' "
                f"using {endpoint}: {exc}.{guidance}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Upsert
    # ------------------------------------------------------------------ #

    async def upsert(
        self,
        chunk_id: str,
        embedding: list[float],
        *,
        document_id: str,
        project_id: str,
        context_label: str | None = None,
        section_title: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Upsert a single chunk embedding."""
        await self.upsert_batch(
            [
                {
                    "chunk_id": chunk_id,
                    "embedding": embedding,
                    "document_id": document_id,
                    "project_id": project_id,
                    "context_label": context_label,
                    "section_title": section_title,
                    "metadata": metadata or {},
                }
            ]
        )

    async def upsert_batch(self, records: list[dict[str, Any]]) -> None:
        """
        Upsert a batch of chunk embeddings.

        Each record must contain:
          chunk_id, embedding, document_id, project_id
        And optionally:
          context_label, section_title, metadata
        """
        if not records:
            return

        client = await self._get_client()
        try:
            from qdrant_client.http.models import PointStruct

            points = [
                PointStruct(
                    id=self._to_qdrant_id(rec["chunk_id"]),
                    vector=rec["embedding"],
                    payload={
                        "chunk_id": rec["chunk_id"],
                        "content": rec.get("content", ""),
                        "document_id": rec["document_id"],
                        "project_id": rec["project_id"],
                        "context_label": rec.get("context_label"),
                        "section_title": rec.get("section_title", ""),
                        "metadata": rec.get("metadata", {}),
                    },
                )
                for rec in records
            ]

            t0 = time.perf_counter()
            await client.upsert(
                collection_name=self._cfg.collection_name,
                points=points,
                wait=True,
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "Upserted %d vectors to Qdrant in %.1f ms.", len(points), elapsed_ms
            )
        except Exception as exc:
            raise VectorStoreError(f"Qdrant upsert failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Delete
    # ------------------------------------------------------------------ #

    async def delete_by_chunk_id(self, chunk_id: str) -> None:
        """Delete a single vector by its chunk UUID."""
        client = await self._get_client()
        try:
            from qdrant_client.http.models import PointIdsList

            await client.delete(
                collection_name=self._cfg.collection_name,
                points_selector=PointIdsList(
                    points=[self._to_qdrant_id(chunk_id)]
                ),
                wait=True,
            )
            logger.debug("Deleted Qdrant vector for chunk_id=%s.", chunk_id)
        except Exception as exc:
            raise VectorStoreError(
                f"Qdrant delete by chunk_id failed: {exc}"
            ) from exc

    async def delete_by_document_id(self, document_id: str) -> None:
        """Delete all vectors belonging to a document."""
        await self._delete_by_filter("document_id", document_id)

    async def delete_by_project_id(self, project_id: str) -> None:
        """Delete all vectors belonging to a project."""
        await self._delete_by_filter("project_id", project_id)

    async def _delete_by_filter(self, field: str, value: str) -> None:
        client = await self._get_client()
        try:
            from qdrant_client.http.models import FieldCondition, Filter, MatchValue

            await client.delete(
                collection_name=self._cfg.collection_name,
                points_selector=Filter(
                    must=[FieldCondition(key=field, match=MatchValue(value=value))]
                ),
                wait=True,
            )
            logger.info(
                "Deleted Qdrant vectors where %s=%s.", field, value
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Qdrant delete by filter ({field}={value}) failed: {exc}"
            ) from exc

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    async def search(
        self,
        query_vector: list[float],
        *,
        top_k: int = 20,
        project_id: str | None = None,
        document_id: str | None = None,
        context_label: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Cosine similarity search with optional payload filters.

        Returns a list of dicts with keys:
          chunk_id, document_id, project_id, context_label,
          section_title, metadata, score
        """
        client = await self._get_client()
        try:
            from qdrant_client.http.models import FieldCondition, Filter, MatchValue

            filter_conditions = []
            if project_id:
                filter_conditions.append(
                    FieldCondition(key="project_id", match=MatchValue(value=project_id))
                )
            if document_id:
                filter_conditions.append(
                    FieldCondition(key="document_id", match=MatchValue(value=document_id))
                )
            if context_label:
                filter_conditions.append(
                    FieldCondition(key="context_label", match=MatchValue(value=context_label))
                )

            query_filter = (
                Filter(must=filter_conditions) if filter_conditions else None
            )

            t0 = time.perf_counter()
            response = await client.query_points(
                collection_name=self._cfg.collection_name,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
            results = response.points
            elapsed_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "Qdrant search returned %d results in %.1f ms.", len(results), elapsed_ms
            )

            return [
                {
                    "chunk_id": hit.payload.get("chunk_id", str(hit.id)),
                    "content": hit.payload.get("content", ""),
                    "document_id": hit.payload.get("document_id", ""),
                    "project_id": hit.payload.get("project_id", ""),
                    "context_label": hit.payload.get("context_label"),
                    "section_title": hit.payload.get("section_title", ""),
                    "metadata": hit.payload.get("metadata", {}),
                    "score": float(hit.score),
                }
                for hit in results
            ]
        except Exception as exc:
            raise VectorStoreError(f"Qdrant search failed: {exc}") from exc

    # ------------------------------------------------------------------ #
    # Re-index
    # ------------------------------------------------------------------ #

    async def reindex_chunk(
        self,
        chunk_id: str,
        embedding: list[float],
        **kwargs: Any,
    ) -> None:
        """Delete then upsert a single chunk (full re-index)."""
        await self.delete_by_chunk_id(chunk_id)
        await self.upsert(chunk_id, embedding, **kwargs)

    # ------------------------------------------------------------------ #
    # Internal
    # ------------------------------------------------------------------ #

    async def _get_client(self) -> Any:
        """Lazy-init the async Qdrant client."""
        global _shared_local_client

        if self._client is None:
            try:
                from qdrant_client import AsyncQdrantClient
            except ImportError as exc:
                raise VectorStoreError(
                    "qdrant-client is required. Install it with: pip install qdrant-client"
                ) from exc

            if self._cfg.host in (":memory:", "memory"):
                if _shared_local_client is None:
                    _shared_local_client = AsyncQdrantClient(location=":memory:")
                self._client = _shared_local_client
            else:
                kwargs: dict[str, Any] = {
                    "host": self._cfg.host,
                    "port": self._cfg.port,
                    "timeout": self._cfg.timeout,
                }
                if self._cfg.api_key:
                    kwargs["api_key"] = self._cfg.api_key
                if self._cfg.use_grpc:
                    kwargs["grpc_port"] = self._cfg.grpc_port
                    kwargs["prefer_grpc"] = True
                self._client = AsyncQdrantClient(**kwargs)
            logger.info(
                "Qdrant client initialised: %s.",
                self._endpoint_description(),
            )

        return self._client

    def _endpoint_description(self) -> str:
        if self._cfg.host in (":memory:", "memory"):
            return "in-memory Qdrant"
        protocol = "gRPC" if self._cfg.use_grpc else "HTTP"
        port = self._cfg.grpc_port if self._cfg.use_grpc else self._cfg.port
        return f"{protocol} endpoint {self._cfg.host}:{port}"

    @staticmethod
    def _to_qdrant_id(chunk_id: str) -> str:
        """
        Qdrant point IDs must be unsigned integers or UUID strings.
        Preserve valid UUIDs and deterministically map other application IDs
        to UUIDs. The original chunk_id remains available in the payload.
        """
        try:
            return str(UUID(chunk_id))
        except (ValueError, AttributeError):
            return str(uuid5(NAMESPACE_URL, f"ba-accelerator:chunk:{chunk_id}"))
