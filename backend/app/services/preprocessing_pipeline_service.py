from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4
from datetime import datetime

from app.schemas import Chunk, PreprocessingPipelineResponse
from dataclasses import asdict
from app.services.import_service import DocumentImportService
from app.utils.logger import get_logger
from app.cache.cache_service import CacheService
import hashlib
import json

logger = get_logger(__name__)


class PreprocessingPipelineError(Exception):
    """Raised when a document preprocessing pipeline stage fails."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"{stage} failed: {message}")


class DocumentImporter(Protocol):
    async def import_document(self, file_path: str | Path) -> str:
        """Parse/import a document and return extracted text."""


class Chunker(Protocol):
    def chunk_text(
        self,
        text: str,
        *,
        document_id: UUID | str | None = None,
        project_id: UUID | str | None = None,
        source: str | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        """Return semantic chunks for parsed text."""


class ContextLabelingStage(Protocol):
    async def label_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        """Return chunks with context labels assigned."""


class RequirementAnalyzer(Protocol):
    async def run(self, chunks: list[dict[str, Any]]) -> Any:
        """Analyze labeled chunks and return structured requirements."""


class DocumentPreprocessingPipelineService:
    """Orchestrates import, chunking, context labeling, and requirement analysis."""

    def __init__(
        self,
        *,
        importer: DocumentImporter | None = None,
        chunker: Chunker | None = None,
        context_labeler: ContextLabelingStage | None = None,
        requirement_analyzer: RequirementAnalyzer | None = None,
        cache_service: CacheService | None = None,
    ) -> None:
        self._importer = importer or DocumentImportService()
        self._chunker = chunker or self._create_default_chunker()
        self._context_labeler = context_labeler or self._create_default_context_labeler()
        self._requirement_analyzer = (
            requirement_analyzer or self._create_default_requirement_analyzer()
        )
        self.cache = cache_service or CacheService()

    async def run(
        self,
        file_path: str | Path,
        *,
        document_id: UUID | str | None = None,
        project_id: UUID | str | None = None,
    ) -> PreprocessingPipelineResponse:
        """Run preprocessing through requirement analysis for a document."""
        source = str(file_path)
        resolved_document_id = self._resolve_uuid(document_id)
        resolved_project_id = self._resolve_uuid(project_id)
        
        # Calculate document hash to check cache
        # For simplicity, hashing the file path and modification time if it's a file
        doc_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
        
        # 1. Check Document Hash Cache before processing
        cached_result = await self.cache.get_parsed_document(doc_hash)
        if cached_result:
            logger.info(f"Cache hit for document {source}")
            from uuid import UUID
            from datetime import datetime
            
            def to_chunk(c: dict) -> Chunk:
                return Chunk(
                    id=UUID(c["id"]) if isinstance(c["id"], str) else c["id"],
                    document_id=UUID(c["document_id"]) if isinstance(c["document_id"], str) else c["document_id"],
                    project_id=UUID(c["project_id"]) if isinstance(c["project_id"], str) else c["project_id"],
                    chunk_index=c["chunk_index"],
                    section_title=c["section_title"],
                    context=c.get("context"),
                    content=c["content"],
                    token_count=c["token_count"],
                    content_hash=c["content_hash"],
                    metadata=c.get("metadata", {}),
                    created_at=datetime.fromisoformat(c["created_at"]) if isinstance(c.get("created_at"), str) else c.get("created_at"),
                )
                
            chunks = [to_chunk(c) for c in cached_result.get("chunks", [])]
            labeled_chunks = [to_chunk(c) for c in cached_result.get("labeled_chunks", [])]
            return PreprocessingPipelineResponse(
                parsed_text=cached_result["parsed_text"],
                chunks=chunks,
                labeled_chunks=labeled_chunks,
                requirement_analysis=cached_result["requirement_analysis"],
            )

        source_metadata = {
            "file_path": source,
            "document_id": str(resolved_document_id),
            "project_id": str(resolved_project_id),
        }

        parsed_text = await self._run_import_stage(file_path)
        chunks = await self._run_chunking_stage(
            parsed_text,
            source,
            source_metadata,
            resolved_document_id,
            resolved_project_id,
        )
        labeled_chunks = await self._run_labeling_stage(chunks)
        requirement_analysis = await self._run_requirement_analysis_stage(labeled_chunks)

        response = PreprocessingPipelineResponse(
            parsed_text=parsed_text,
            chunks=chunks,
            labeled_chunks=labeled_chunks,
            requirement_analysis=requirement_analysis,
        )
        
        # Store parsing result in cache if miss
        await self.cache.set_parsed_document(doc_hash, asdict(response), ttl=86400)
        
        return response

    async def _run_import_stage(self, file_path: str | Path) -> str:
        try:
            return await self._importer.import_document(file_path)
        except Exception as exc:
            logger.error("Import stage failed: %s", exc, exc_info=True)
            raise PreprocessingPipelineError("Import Service", str(exc)) from exc

    async def _run_chunking_stage(
        self,
        parsed_text: str,
        source: str,
        source_metadata: dict[str, Any],
        document_id: UUID,
        project_id: UUID,
    ) -> list[Chunk]:
        try:
            return self._chunker.chunk_text(
                parsed_text,
                document_id=document_id,
                project_id=project_id,
                source=source,
                source_metadata=source_metadata,
            )
        except Exception as exc:
            logger.error("Semantic chunking stage failed: %s", exc, exc_info=True)
            raise PreprocessingPipelineError("Semantic Chunking", str(exc)) from exc

    async def _run_labeling_stage(self, chunks: list[Chunk]) -> list[Chunk]:
        try:
            return await self._context_labeler.label_chunks(chunks)
        except Exception as exc:
            logger.error("Context labeling stage failed: %s", exc, exc_info=True)
            raise PreprocessingPipelineError("Context Labeling", str(exc)) from exc

    async def _run_requirement_analysis_stage(self, chunks: list[Chunk]) -> Any:
        try:
            return await self._requirement_analyzer.run(self._serialize_chunks(chunks))
        except Exception as exc:
            logger.error("Requirement analysis stage failed: %s", exc, exc_info=True)
            raise PreprocessingPipelineError("Requirement Analysis Agent", str(exc)) from exc

    def _serialize_chunks(self, chunks: list[Chunk]) -> list[dict[str, Any]]:
        return [self._chunk_to_dict(chunk) for chunk in chunks]

    def _chunk_to_dict(self, chunk: Chunk) -> dict[str, Any]:
        return {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "project_id": str(chunk.project_id),
            "chunk_index": chunk.chunk_index,
            "section_title": chunk.section_title,
            "content": chunk.content,
            "token_count": chunk.token_count,
            "context": chunk.context,
            "content_hash": chunk.content_hash,
            "metadata": self._json_safe(chunk.metadata),
            "created_at": chunk.created_at.isoformat(),
        }

    def _resolve_uuid(self, value: UUID | str | None) -> UUID:
        if value is None:
            return uuid4()
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except ValueError:
            from uuid import uuid5, NAMESPACE_DNS
            return uuid5(NAMESPACE_DNS, str(value))

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        return value

    def _create_default_chunker(self) -> Chunker:
        from app.chunking.chunk_service import ChunkService

        return ChunkService()

    def _create_default_context_labeler(self) -> ContextLabelingStage:
        from app.labeling.context_labeler import ContextLabeler

        return ContextLabeler()

    def _create_default_requirement_analyzer(self) -> RequirementAnalyzer:
        from app.agents.requirement_analysis_agent import RequirementAnalysisAgent

        # pyrefly: ignore [bad-instantiation]
        return RequirementAnalysisAgent()
