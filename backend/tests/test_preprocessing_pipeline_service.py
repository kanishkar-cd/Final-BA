from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import sys
from typing import Any
from uuid import UUID
import pytest

@pytest.fixture(autouse=True)
def clear_cache():
    from app.cache.cache_manager import CacheManager
    CacheManager._memory_cache.clear()

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import Chunk
from app.services.preprocessing_pipeline_service import (
    DocumentPreprocessingPipelineService,
    PreprocessingPipelineError,
)


DOCUMENT_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")


class FakeImporter:
    def __init__(self, parsed_text: str = "Parsed document text.") -> None:
        self.parsed_text = parsed_text
        self.calls: list[str | Path] = []

    async def import_document(self, file_path: str | Path) -> str:
        self.calls.append(file_path)
        return self.parsed_text


class FakeChunker:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chunk_text(
        self,
        text: str,
        *,
        document_id: UUID | str | None = None,
        project_id: UUID | str | None = None,
        source: str | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> list[Chunk]:
        self.calls.append(
            {
                "text": text,
                "document_id": document_id,
                "project_id": project_id,
                "source": source,
                "source_metadata": source_metadata,
            }
        )
        return [
            Chunk.create(
                document_id=UUID(str(document_id)),
                project_id=UUID(str(project_id)),
                chunk_index=0,
                section_title="Authentication",
                content="Users can sign in with OTP.",
                token_count=7,
                context=None,
                metadata={
                    "sequence_number": 1,
                    "source": source,
                    "source_metadata": source_metadata or {},
                },
            )
        ]


class FakeContextLabeler:
    def __init__(self) -> None:
        self.calls: list[list[Chunk]] = []

    async def label_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        self.calls.append(chunks)
        return [replace(chunk, context="Authentication") for chunk in chunks]


class FakeRequirementAnalyzer:
    def __init__(self) -> None:
        self.calls: list[list[dict[str, Any]]] = []

    async def run(self, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(chunks)
        return {
            "actors": ["User"],
            "functional_requirements": ["Users can sign in with OTP."],
            "non_functional_requirements": [],
            "dependencies": ["OTP Service"],
            "business_goals": ["Secure access"],
            "edge_cases": ["OTP expires before the user completes sign-in."],
            "constraints": ["OTP delivery depends on the configured provider."],
        }


def make_pipeline(
    *,
    importer: Any | None = None,
    chunker: Any | None = None,
    labeler: Any | None = None,
    analyzer: Any | None = None,
) -> DocumentPreprocessingPipelineService:
    return DocumentPreprocessingPipelineService(
        importer=importer or FakeImporter(),
        chunker=chunker or FakeChunker(),
        context_labeler=labeler or FakeContextLabeler(),
        requirement_analyzer=analyzer or FakeRequirementAnalyzer(),
    )


def test_pipeline_orchestrates_all_stages_and_preserves_metadata() -> None:
    importer = FakeImporter("Parsed text from parser.")
    chunker = FakeChunker()
    labeler = FakeContextLabeler()
    analyzer = FakeRequirementAnalyzer()
    pipeline = make_pipeline(
        importer=importer,
        chunker=chunker,
        labeler=labeler,
        analyzer=analyzer,
    )

    response = asyncio.run(
        pipeline.run(
            "sample.txt",
            document_id=DOCUMENT_ID,
            project_id=PROJECT_ID,
        )
    )

    assert importer.calls == ["sample.txt"]
    assert chunker.calls == [
        {
            "text": "Parsed text from parser.",
            "document_id": DOCUMENT_ID,
            "project_id": PROJECT_ID,
            "source": "sample.txt",
            "source_metadata": {
                "file_path": "sample.txt",
                "document_id": str(DOCUMENT_ID),
                "project_id": str(PROJECT_ID),
            },
        }
    ]
    assert labeler.calls == [response.chunks]
    assert analyzer.calls == [
        [
            {
                "chunk_id": str(response.labeled_chunks[0].id),
                "document_id": str(DOCUMENT_ID),
                "project_id": str(PROJECT_ID),
                "chunk_index": 0,
                "section_title": "Authentication",
                "content": "Users can sign in with OTP.",
                "token_count": 7,
                "context": "Authentication",
                "content_hash": response.labeled_chunks[0].content_hash,
                "metadata": {
                    "sequence_number": 1,
                    "source": "sample.txt",
                    "source_metadata": {
                        "file_path": "sample.txt",
                        "document_id": str(DOCUMENT_ID),
                        "project_id": str(PROJECT_ID),
                    },
                },
                "created_at": response.labeled_chunks[0].created_at.isoformat(),
            }
        ]
    ]
    assert response.parsed_text == "Parsed text from parser."
    assert response.chunks[0].context is None
    assert response.labeled_chunks[0].context == "Authentication"
    assert response.requirement_analysis["actors"] == ["User"]
    assert response.requirement_analysis["edge_cases"] == [
        "OTP expires before the user completes sign-in."
    ]
    assert response.requirement_analysis["constraints"] == [
        "OTP delivery depends on the configured provider."
    ]


def test_pipeline_wraps_import_errors_with_stage_name() -> None:
    class FailingImporter:
        async def import_document(self, file_path: str | Path) -> str:
            raise FileNotFoundError(f"missing: {file_path}")

    pipeline = make_pipeline(importer=FailingImporter())

    try:
        asyncio.run(pipeline.run("missing.txt"))
    except PreprocessingPipelineError as exc:
        assert exc.stage == "Import Service"
        assert "missing.txt" in str(exc)
    else:
        raise AssertionError("Expected PreprocessingPipelineError")


def test_pipeline_wraps_chunking_errors_with_stage_name() -> None:
    class FailingChunker:
        def chunk_text(self, *_: Any, **__: Any) -> list[Chunk]:
            raise RuntimeError("embedding model unavailable")

    pipeline = make_pipeline(chunker=FailingChunker())

    try:
        asyncio.run(pipeline.run("sample.txt"))
    except PreprocessingPipelineError as exc:
        assert exc.stage == "Semantic Chunking"
        assert "embedding model unavailable" in str(exc)
    else:
        raise AssertionError("Expected PreprocessingPipelineError")


def test_pipeline_wraps_context_labeling_errors_with_stage_name() -> None:
    class FailingLabeler:
        async def label_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
            raise RuntimeError("invalid label response")

    pipeline = make_pipeline(labeler=FailingLabeler())

    try:
        asyncio.run(pipeline.run("sample.txt"))
    except PreprocessingPipelineError as exc:
        assert exc.stage == "Context Labeling"
        assert "invalid label response" in str(exc)
    else:
        raise AssertionError("Expected PreprocessingPipelineError")


def test_pipeline_wraps_requirement_analysis_errors_with_stage_name() -> None:
    class FailingAnalyzer:
        async def run(self, chunks: list[dict[str, Any]]) -> dict[str, Any]:
            raise RuntimeError("llm unavailable")

    pipeline = make_pipeline(analyzer=FailingAnalyzer())

    try:
        asyncio.run(pipeline.run("sample.txt"))
    except PreprocessingPipelineError as exc:
        assert exc.stage == "Requirement Analysis Agent"
        assert "llm unavailable" in str(exc)
    else:
        raise AssertionError("Expected PreprocessingPipelineError")
