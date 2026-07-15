"""
RAG (Retrieval-Augmented Generation) infrastructure package.

Exposes the high-level services used by the API layer and agent integrations.
"""

from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store_service import VectorStoreService
from app.rag.bm25_service import BM25Service
from app.rag.dense_retrieval_service import DenseRetrievalService
from app.rag.hybrid_retrieval_service import HybridRetrievalService
from app.rag.rrf_service import RRFService
from app.rag.reranker_service import RerankerService
from app.rag.context_builder import ContextBuilder
from app.rag.indexing_service import IndexingService

__all__ = [
    "EmbeddingService",
    "VectorStoreService",
    "BM25Service",
    "DenseRetrievalService",
    "HybridRetrievalService",
    "RRFService",
    "RerankerService",
    "ContextBuilder",
    "IndexingService",
]
