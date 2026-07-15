"""
Pydantic schemas for the RAG infrastructure layer.

Covers all four API endpoints:
  POST /api/rag/index          - trigger embedding + vector indexing for chunks
  POST /api/rag/search         - hybrid BM25 + dense search, returns raw results
  POST /api/rag/context        - full pipeline to LLM-ready context package
  POST /api/rag/traceability   - traceability retrieval for Agent 4 validation
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared primitives
# ─────────────────────────────────────────────────────────────────────────────


class ChunkIndexInput(BaseModel):
    """A single chunk to be embedded and indexed."""

    chunk_id: str = Field(description="Unique chunk identifier (UUID string).")
    document_id: str = Field(description="Parent document identifier.")
    project_id: str = Field(description="Parent project identifier.")
    content: str = Field(description="Text content of the chunk.")
    section_title: str = Field(default="", description="Section heading from the source document.")
    context_label: str | None = Field(
        default=None,
        description="Business-domain context label assigned by the labeling service.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievedChunkResult(BaseModel):
    """A single retrieved chunk with its retrieval score."""

    chunk_id: str
    document_id: str
    project_id: str
    content: str
    section_title: str = ""
    context_label: str | None = None
    score: float = Field(description="Retrieval score (BM25 rank, cosine similarity, or RRF).")
    rank: int = Field(description="1-based rank within the result set.")
    source: str = Field(
        default="unknown",
        description="Which retrieval method produced this result: bm25, dense, rrf, reranked.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/rag/index
# ─────────────────────────────────────────────────────────────────────────────


class IndexRequest(BaseModel):
    """Request body for chunk embedding and vector indexing."""

    chunks: list[ChunkIndexInput] = Field(
        description="One or more chunks to embed and store.",
        min_length=1,
    )
    reindex: bool = Field(
        default=False,
        description="Force re-embedding even if the chunk is already indexed.",
    )


class IndexResponse(BaseModel):
    """Response after indexing chunks."""

    indexed_count: int = Field(description="Number of chunks successfully indexed.")
    skipped_count: int = Field(description="Chunks skipped because they were already indexed.")
    failed_count: int = Field(description="Chunks that failed to index.")
    failed_chunk_ids: list[str] = Field(default_factory=list)
    duration_ms: float = Field(description="Total wall-clock time for the indexing run.")


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/rag/search
# ─────────────────────────────────────────────────────────────────────────────


class SearchFilters(BaseModel):
    """Optional metadata filters applied to both BM25 and dense searches."""

    project_id: str | None = None
    document_id: str | None = None
    context_label: str | None = None


class SearchRequest(BaseModel):
    """Request body for hybrid BM25 + dense search."""

    query: str = Field(description="Free-text search query.")
    filters: SearchFilters = Field(default_factory=SearchFilters)
    bm25_top_k: int = Field(default=20, ge=1, le=100)
    dense_top_k: int = Field(default=20, ge=1, le=100)


class SearchResponse(BaseModel):
    """Raw results from both retrieval arms before fusion."""

    query: str
    bm25_results: list[RetrievedChunkResult] = Field(default_factory=list)
    dense_results: list[RetrievedChunkResult] = Field(default_factory=list)
    fused_results: list[RetrievedChunkResult] = Field(default_factory=list)
    bm25_latency_ms: float = 0.0
    dense_latency_ms: float = 0.0
    fusion_latency_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/rag/context
# ─────────────────────────────────────────────────────────────────────────────


class ContextRequest(BaseModel):
    """
    Request body for the full retrieval pipeline that feeds Agent 3.

    Mirrors the Agent 2 output shape so it can be passed through directly.
    """

    epic: str = Field(description="Epic title from Agent 2.")
    feature: str = Field(description="Feature title from Agent 2.")
    requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement codes (e.g. FR-001) referenced by this feature.",
    )
    project_id: str | None = Field(
        default=None,
        description="Scope retrieval to a specific project.",
    )
    document_id: str | None = Field(
        default=None,
        description="Scope retrieval to a specific document.",
    )
    # Override pipeline defaults per-call
    dense_top_k: int = Field(default=20, ge=1, le=100)
    bm25_top_k: int = Field(default=20, ge=1, le=100)
    rrf_k: int = Field(default=60, ge=1)
    reranker_candidates: int = Field(default=20, ge=1, le=100)
    reranker_final: int = Field(default=5, ge=1, le=50)


class SupportingRequirement(BaseModel):
    """A requirement referenced by source chunks in the context package."""

    id: str
    description: str
    source: str | None = None


class ContextPackage(BaseModel):
    """
    LLM-ready context package consumed by Agent 3 for story generation.

    Preserves full traceability through chunk IDs and document IDs.
    """

    epic: str
    feature: str
    source_chunks: list[RetrievedChunkResult] = Field(default_factory=list)
    supporting_requirements: list[SupportingRequirement] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    # Retrieval provenance for audit / confidence scoring
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)


class ContextResponse(BaseModel):
    """Response wrapping the LLM-ready context package."""

    retrieved_context: ContextPackage
    pipeline_latency_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/rag/traceability
# ─────────────────────────────────────────────────────────────────────────────


class TraceabilityRequest(BaseModel):
    """
    Request body for traceability retrieval that grounds Agent 4 validation.
    """

    story_id: str = Field(description="User story identifier (e.g. US-001).")
    story_text: str = Field(description="Full text of the generated user story.")
    requirement_ids: list[str] = Field(
        default_factory=list,
        description="Requirement codes that the story claims to address.",
    )
    project_id: str | None = None
    document_id: str | None = None
    top_k: int = Field(default=10, ge=1, le=50)


class TraceabilityResponse(BaseModel):
    """
    Grounding package returned to Agent 4 for validation.

    Contains the source chunks and requirements the story should be checked
    against, plus any inferred dependencies and business rules.
    """

    story_id: str
    source_chunks: list[RetrievedChunkResult] = Field(default_factory=list)
    source_requirements: list[SupportingRequirement] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    retrieval_latency_ms: float = 0.0
