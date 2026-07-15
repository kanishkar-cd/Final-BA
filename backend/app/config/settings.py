from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SemanticChunkingSettings:
    """Configuration for semantic document chunking."""

    maximum_chunk_tokens: int = int(os.getenv("CHUNK_MAX_TOKENS", "300"))
    minimum_chunk_tokens: int = int(os.getenv("CHUNK_MIN_TOKENS", "90"))
    embedding_model_name: str = os.getenv(
        "SEMANTIC_CHUNKING_MODEL_NAME",
        "sentence-transformers/all-MiniLM-L6-v2",
    )
    similarity_threshold: float = float(
        os.getenv("SEMANTIC_CHUNKING_SIMILARITY_THRESHOLD", "0.65")
    )


@dataclass(frozen=True)
class QdrantSettings:
    """Configuration for Qdrant vector database."""

    host: str = os.getenv("QDRANT_HOST", "localhost")
    port: int = int(os.getenv("QDRANT_PORT", "6333"))
    grpc_port: int = int(os.getenv("QDRANT_GRPC_PORT", "6334"))
    api_key: str | None = os.getenv("QDRANT_API_KEY") or None
    use_grpc: bool = os.getenv("QDRANT_USE_GRPC", "false").lower() == "true"
    collection_name: str = os.getenv("QDRANT_COLLECTION_NAME", "brd_chunks")
    # Vector dimension for BAAI/bge-base-en-v1.5
    vector_size: int = int(os.getenv("QDRANT_VECTOR_SIZE", "768"))
    timeout: float = float(os.getenv("QDRANT_TIMEOUT", "30.0"))


@dataclass(frozen=True)
class EmbeddingSettings:
    """Configuration for embedding generation."""

    model_name: str = os.getenv(
        "EMBEDDING_MODEL_NAME",
        "BAAI/bge-base-en-v1.5",
    )
    batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
    # Maximum number of retries on transient failures
    max_retries: int = int(os.getenv("EMBEDDING_MAX_RETRIES", "3"))
    retry_delay_seconds: float = float(os.getenv("EMBEDDING_RETRY_DELAY", "1.0"))
    # Cache embeddings in Redis during indexing
    cache_enabled: bool = os.getenv("EMBEDDING_CACHE_ENABLED", "true").lower() == "true"


@dataclass(frozen=True)
class RerankerSettings:
    """Configuration for cross-encoder reranking."""

    model_name: str = os.getenv(
        "RERANKER_MODEL_NAME",
        "BAAI/bge-reranker-base",
    )
    # Number of candidates fed to the cross-encoder
    candidate_count: int = int(os.getenv("RERANKER_CANDIDATE_COUNT", "20"))
    # Number of top results returned after reranking
    final_count: int = int(os.getenv("RERANKER_FINAL_COUNT", "5"))


@dataclass(frozen=True)
class RetrievalSettings:
    """Configuration for hybrid retrieval pipeline."""

    # Dense retrieval top-k before fusion
    dense_top_k: int = int(os.getenv("RETRIEVAL_DENSE_TOP_K", "20"))
    # BM25 top-k before fusion
    bm25_top_k: int = int(os.getenv("RETRIEVAL_BM25_TOP_K", "20"))
    # RRF k constant (higher = less rank compression)
    rrf_k: int = int(os.getenv("RETRIEVAL_RRF_K", "60"))
    # PostgreSQL DSN for BM25 full-text search
    postgres_dsn: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/ba_accelerator",
    )


@dataclass(frozen=True)
class ContextAssemblySettings:
    """B1: Per-agent context assembly configuration."""
    segmentation_neighbor_window: int = int(os.getenv("SEGMENTATION_NEIGHBOR_WINDOW", "1"))
    epic_rollup_max_chars: int = int(os.getenv("EPIC_ROLLUP_MAX_CHARS", "2000"))


@dataclass(frozen=True)
class ProviderModelLimits:
    """B4.4: Dynamic budget configuration based on active provider and model."""
    provider: str
    model: str
    rpm: int
    rpd: int | None
    tpm: int | None
    tpd: int | None
    safe_call_ceiling: int


@dataclass(frozen=True)
class ModelRoutingSettings:
    """B4.2: Agent -> ordered fallback chain of (provider, model)."""
    segmentation_chain: tuple[tuple[str, str], ...] = (
        ("groq", "llama-3.1-8b-instant"),
        ("groq", "qwen/qwen3-32b"),
    )
    epic_chain: tuple[tuple[str, str], ...] = (
        ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    )
    user_story_chain: tuple[tuple[str, str], ...] = (
        ("groq", "meta-llama/llama-4-scout-17b-16e-instruct"),
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    )
    validation_chain: tuple[tuple[str, str], ...] = (
        ("groq", "llama-3.3-70b-versatile"),
        ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
    )


@dataclass(frozen=True)
class Settings:
    """Application settings."""

    semantic_chunking: SemanticChunkingSettings = field(
        default_factory=SemanticChunkingSettings
    )
    context_labeling_batch_size: int = int(
        os.getenv("CONTEXT_LABELING_BATCH_SIZE", "10")
    )
    context_labeling_max_tokens: int = int(
        os.getenv("CONTEXT_LABELING_MAX_TOKENS", "1000")
    )
    qdrant: QdrantSettings = field(default_factory=QdrantSettings)
    embedding: EmbeddingSettings = field(default_factory=EmbeddingSettings)
    reranker: RerankerSettings = field(default_factory=RerankerSettings)
    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    
    # Part B config
    context_assembly: ContextAssemblySettings = field(default_factory=ContextAssemblySettings)
    model_routing: ModelRoutingSettings = field(default_factory=ModelRoutingSettings)


settings = Settings()
