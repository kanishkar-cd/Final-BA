from __future__ import annotations

from pathlib import Path
import sys
from typing import Sequence
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chunking.chunk_service import (
    ChunkService,
    SentenceTransformerEmbeddingModel,
    chunk_text,
)
from app.config.settings import SemanticChunkingSettings
from app.schemas import Chunk


DOCUMENT_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")


class FakeEmbeddingModel:
    """Deterministic sentence embeddings for semantic chunking tests."""

    def encode(self, sentences: Sequence[str]) -> list[list[float]]:
        return [self._embedding_for(sentence) for sentence in sentences]

    def _embedding_for(self, sentence: str) -> list[float]:
        lower_sentence = sentence.lower()
        if any(term in lower_sentence for term in ("payment", "invoice", "billing")):
            return [0.0, 1.0, 0.0]
        if any(term in lower_sentence for term in ("report", "dashboard", "analytics")):
            return [0.0, 0.0, 1.0]
        return [1.0, 0.0, 0.0]


class CountingEmbeddingModel(FakeEmbeddingModel):
    def __init__(self) -> None:
        self.calls = 0

    def encode(self, sentences: Sequence[str]) -> list[list[float]]:
        self.calls += 1
        return super().encode(sentences)


def make_service(
    max_tokens: int | None = None,
    similarity_threshold: float = 0.7,
    min_tokens: int = 0,
) -> ChunkService:
    return ChunkService(
        max_tokens=max_tokens,
        embedding_model=FakeEmbeddingModel(),
        similarity_threshold=similarity_threshold,
        min_tokens=min_tokens,
    )


def test_chunk_text_returns_chunk_schema_objects() -> None:
    chunks = chunk_text(
        "Overview. This document describes account onboarding.",
        document_id=DOCUMENT_ID,
        project_id=PROJECT_ID,
        source="sample.txt",
        embedding_model=FakeEmbeddingModel(),
        min_tokens=0,
    )

    assert len(chunks) == 1
    assert isinstance(chunks[0], Chunk)
    assert chunks[0].document_id == DOCUMENT_ID
    assert chunks[0].project_id == PROJECT_ID
    assert chunks[0].chunk_index == 0
    assert len(chunks[0].content_hash) == 64
    assert chunks[0].content == "Overview. This document describes account onboarding."
    assert chunks[0].context is None
    assert chunks[0].metadata["sequence_number"] == 1
    assert chunks[0].metadata["source"] == "sample.txt"
    assert chunks[0].token_count > 0


def test_merges_consecutive_sentences_based_on_semantic_similarity() -> None:
    text = """
Users can upload source documents for analysis. The parser extracts plain text from each file.
Payment invoices are reconciled with billing records. Billing exceptions require manual review.
"""

    chunks = make_service().chunk_text(text, source="requirements.docx")

    assert [chunk.metadata["sequence_number"] for chunk in chunks] == [1, 2]
    assert chunks[0].content == (
        "Users can upload source documents for analysis. "
        "The parser extracts plain text from each file."
    )
    assert chunks[1].content == (
        "Payment invoices are reconciled with billing records. "
        "Billing exceptions require manual review."
    )


def test_semantic_groups_split_at_sentence_boundaries_when_over_token_limit() -> None:
    text = """
Users can upload source documents for analysis. The parser extracts plain text from each file.
The chunking service groups related statements together.
The analysis agent evaluates each grouped statement.
Generated requirements keep traceability metadata.
"""

    chunks = make_service(max_tokens=18).chunk_text(text)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 18 for chunk in chunks)
    assert chunks[0].content.endswith("The parser extracts plain text from each file.")
    assert chunks[1].content == (
        "The chunking service groups related statements together. "
        "The analysis agent evaluates each grouped statement."
    )
    assert chunks[2].content == "Generated requirements keep traceability metadata."
    assert ". The " in chunks[1].content
    assert chunks[1].content != (
        "The analysis agent evaluates each grouped statement. "
        "Generated requirements keep traceability metadata."
    )


def test_starts_new_chunk_when_similarity_falls_below_threshold() -> None:
    text = (
        "Users can import documents. Imported documents are parsed into sentences. "
        "Analytics dashboards show monthly report trends."
    )

    chunks = make_service(similarity_threshold=0.8).chunk_text(text)

    assert len(chunks) == 2
    assert chunks[0].content == (
        "Users can import documents. Imported documents are parsed into sentences."
    )
    assert chunks[1].content == "Analytics dashboards show monthly report trends."


def test_uses_semantic_chunking_settings_for_model_and_threshold() -> None:
    service = ChunkService(
        chunking_settings=SemanticChunkingSettings(
            maximum_chunk_tokens=210,
            minimum_chunk_tokens=84,
            embedding_model_name="custom-semantic-model",
            similarity_threshold=0.91,
        )
    )

    assert service.max_tokens == 210
    assert service.similarity_threshold == 0.91
    assert service.min_tokens == 84
    assert isinstance(service.embedding_model, SentenceTransformerEmbeddingModel)
    assert service.embedding_model.model_name == "custom-semantic-model"


def test_merges_tiny_chunks_with_related_adjacent_chunks_when_they_fit() -> None:
    text = (
        "Users import documents. Payment invoices are reviewed. "
        "Billing records are matched. Analytics dashboards show trends."
    )

    chunks = make_service(min_tokens=10).chunk_text(text)

    assert len(chunks) == 3
    assert chunks[0].content == "Users import documents."
    assert chunks[1].content == (
        "Payment invoices are reviewed. Billing records are matched."
    )
    assert chunks[2].content == "Analytics dashboards show trends."


def test_does_not_merge_tiny_chunks_past_max_token_limit() -> None:
    text = (
        "Payment invoices are reviewed carefully. "
        "Billing exceptions require manual approval. "
        "Invoice evidence is archived."
    )

    chunks = make_service(max_tokens=9, min_tokens=8).chunk_text(text)

    assert len(chunks) == 3
    assert all(chunk.token_count <= 9 for chunk in chunks)


def test_semantic_chunking_embeds_document_in_one_batch() -> None:
    model = CountingEmbeddingModel()
    service = ChunkService(
        embedding_model=model,
        max_tokens=12,
        min_tokens=8,
        similarity_threshold=0.7,
    )

    service.chunk_text(
        "Users import documents. Imported documents are parsed. "
        "The parser extracts requirements. Requirements retain traceability."
    )

    assert model.calls == 1
