"""
RAG API Router.

Exposes four endpoints under the /api/rag prefix:

  POST /api/rag/index          – embed + store chunks in Qdrant / update BM25 index
  POST /api/rag/search         – hybrid BM25 + dense search, returns raw result sets
  POST /api/rag/context        – full pipeline → LLM-ready context package (Agent 3)
  POST /api/rag/traceability   – grounding retrieval for story validation (Agent 4)

All services are constructed once at module load via module-level singletons
(lazy model loading means there is no startup cost until first request).
Query results for /search, /context, and /traceability are cached in Redis
for 15 minutes using the helpers in database/redis/cache.py.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from app.database.redis.cache import (
    cache_rag_context_result,
    cache_rag_search_result,
    cache_rag_traceability_result,
    get_cached_rag_context_result,
    get_cached_rag_search_result,
    get_cached_rag_traceability_result,
)
from app.rag.bm25_service import BM25Service
from app.rag.context_builder import ContextBuilder
from app.rag.dense_retrieval_service import DenseRetrievalService
from app.rag.embedding_service import EmbeddingService
from app.rag.hybrid_retrieval_service import HybridRetrievalService
from app.rag.indexing_service import IndexingService
from app.rag.reranker_service import RerankerService
from app.rag.rrf_service import RRFService
from app.rag.vector_store_service import VectorStoreService
from app.schemas.rag import (
    ContextRequest,
    ContextResponse,
    IndexRequest,
    IndexResponse,
    SearchRequest,
    SearchResponse,
    TraceabilityRequest,
    TraceabilityResponse,
)
from app.schemas.user_story import ApiResponse

logger = logging.getLogger("api.rag")

# ─────────────────────────────────────────────────────────────────────────────
# Lazy service accessors — instantiated on first request, not at import time.
# This prevents a missing Qdrant / embedding model from crashing the whole app.
# ─────────────────────────────────────────────────────────────────────────────

_svc: dict[str, Any] = {}


def _get_embedding_service() -> Any:
    if "embedding" not in _svc:
        _svc["embedding"] = EmbeddingService()
    return _svc["embedding"]


def _get_vector_store() -> Any:
    if "vector_store" not in _svc:
        _svc["vector_store"] = VectorStoreService()
    return _svc["vector_store"]


def _get_bm25_service() -> Any:
    if "bm25" not in _svc:
        _svc["bm25"] = BM25Service()
    return _svc["bm25"]


def _get_dense_service() -> Any:
    if "dense" not in _svc:
        _svc["dense"] = DenseRetrievalService(_get_embedding_service(), _get_vector_store())
    return _svc["dense"]


def _get_hybrid_service() -> Any:
    if "hybrid" not in _svc:
        _svc["hybrid"] = HybridRetrievalService(_get_bm25_service(), _get_dense_service())
    return _svc["hybrid"]


def _get_rrf_service() -> Any:
    if "rrf" not in _svc:
        _svc["rrf"] = RRFService()
    return _svc["rrf"]


def _get_reranker_service() -> Any:
    if "reranker" not in _svc:
        _svc["reranker"] = RerankerService()
    return _svc["reranker"]


def _get_context_builder() -> Any:
    if "context_builder" not in _svc:
        _svc["context_builder"] = ContextBuilder()
    return _svc["context_builder"]


def _get_indexing_service() -> Any:
    if "indexing" not in _svc:
        _svc["indexing"] = IndexingService(_get_embedding_service(), _get_vector_store())
    return _svc["indexing"]

# ─────────────────────────────────────────────────────────────────────────────
# Router
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/rag", tags=["RAG Infrastructure"])


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/rag/index
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/index",
    response_model=ApiResponse,
    summary="Embed and index document chunks",
    description=(
        "Generates dense embeddings for each chunk and stores them in the "
        "Qdrant brd_chunks collection. Also writes context_label and "
        "embedding_indexed_at back to PostgreSQL so BM25 search stays "
        "consistent. Skips already-indexed chunks unless reindex=true."
    ),
)
async def index_chunks(request: IndexRequest) -> ApiResponse:
    try:
        result: IndexResponse = await _get_indexing_service().index_chunks(
            request.chunks,
            reindex=request.reindex,
        )
        return ApiResponse(
            success=True,
            message=(
                f"Indexing complete: {result.indexed_count} indexed, "
                f"{result.skipped_count} skipped, {result.failed_count} failed."
            ),
            data=result.model_dump(),
        )
    except Exception as exc:
        logger.error("RAG indexing failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Indexing failed: {exc}",
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/rag/search
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/search",
    response_model=ApiResponse,
    summary="Hybrid BM25 + dense search",
    description=(
        "Runs BM25 (PostgreSQL FTS) and dense (Qdrant) retrieval in parallel "
        "for the supplied query, fuses the results with RRF, and returns all "
        "three result sets. Results are cached for 15 minutes."
    ),
)
async def hybrid_search(request: SearchRequest) -> ApiResponse:
    # Build a cache-key-friendly filters dict
    filters: dict[str, Any] = {
        "project_id": request.filters.project_id,
        "document_id": request.filters.document_id,
        "context_label": request.filters.context_label,
        "bm25_top_k": request.bm25_top_k,
        "dense_top_k": request.dense_top_k,
    }

    # ── Cache hit ──────────────────────────────────────────────────────
    cached = await _try_get_cached_search(request.query, filters)
    if cached is not None:
        return ApiResponse(success=True, message="Hybrid search result (cached).", data=cached)

    # ── Live retrieval ─────────────────────────────────────────────────
    try:
        t0 = time.perf_counter()

        hybrid_result = await _get_hybrid_service().retrieve_by_query(
            request.query,
            project_id=request.filters.project_id,
            document_id=request.filters.document_id,
            bm25_top_k=request.bm25_top_k,
            dense_top_k=request.dense_top_k,
        )

        fused = _get_rrf_service().fuse(
            hybrid_result.bm25_results,
            hybrid_result.dense_results,
        )

        fusion_ms = (time.perf_counter() - t0) * 1000

        response = SearchResponse(
            query=request.query,
            bm25_results=hybrid_result.bm25_results,
            dense_results=hybrid_result.dense_results,
            fused_results=fused,
            bm25_latency_ms=hybrid_result.bm25_latency_ms,
            dense_latency_ms=hybrid_result.dense_latency_ms,
            fusion_latency_ms=fusion_ms,
        )

        result_dict = response.model_dump()
        await _try_cache_search(request.query, filters, result_dict)

        return ApiResponse(
            success=True,
            message=f"Hybrid search returned {len(fused)} fused results.",
            data=result_dict,
        )

    except Exception as exc:
        logger.error("RAG search failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {exc}",
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/rag/context
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/context",
    response_model=ApiResponse,
    summary="Retrieve LLM-ready context package for story generation",
    description=(
        "Full pipeline: hybrid retrieval → RRF → cross-encoder reranking → "
        "context builder. Returns a ContextPackage with source chunks, "
        "requirements, dependencies, and business rules for Agent 3. "
        "Results are cached for 15 minutes."
    ),
)
async def retrieve_context(request: ContextRequest) -> ApiResponse:
    filters: dict[str, Any] = {
        "epic": request.epic,
        "feature": request.feature,
        "requirement_ids": sorted(request.requirement_ids),
        "project_id": request.project_id,
        "document_id": request.document_id,
        "reranker_final": request.reranker_final,
    }

    # ── Cache hit ──────────────────────────────────────────────────────
    query_str = f"{request.epic} {request.feature}"
    cached = await _try_get_cached_context(query_str, filters)
    if cached is not None:
        return ApiResponse(
            success=True,
            message="Context package retrieved (cached).",
            data=cached,
        )

    # ── Live pipeline ──────────────────────────────────────────────────
    try:
        t0 = time.perf_counter()

        # 1. Hybrid retrieval
        hybrid_result = await _get_hybrid_service().retrieve(
            epic=request.epic,
            feature=request.feature,
            requirement_ids=request.requirement_ids,
            project_id=request.project_id,
            document_id=request.document_id,
            bm25_top_k=request.bm25_top_k,
            dense_top_k=request.dense_top_k,
        )

        # 2. RRF fusion
        fused = _get_rrf_service().fuse(
            hybrid_result.bm25_results,
            hybrid_result.dense_results,
            rrf_k=request.rrf_k,
            top_k=request.reranker_candidates,
        )

        # 3. Cross-encoder reranking
        reranked = await _get_reranker_service().rerank(
            query_str,
            fused,
            candidate_count=request.reranker_candidates,
            final_count=request.reranker_final,
        )

        # 4. Build context package
        pipeline_ms = (time.perf_counter() - t0) * 1000
        context_package = _get_context_builder().build_context_package(
            epic=request.epic,
            feature=request.feature,
            reranked_chunks=reranked,
            requirement_ids=request.requirement_ids,
            retrieval_metadata={
                "bm25_latency_ms": hybrid_result.bm25_latency_ms,
                "dense_latency_ms": hybrid_result.dense_latency_ms,
                "pipeline_latency_ms": pipeline_ms,
                "bm25_count": len(hybrid_result.bm25_results),
                "dense_count": len(hybrid_result.dense_results),
                "fused_count": len(fused),
                "reranked_count": len(reranked),
            },
        )

        response = ContextResponse(
            retrieved_context=context_package,
            pipeline_latency_ms=pipeline_ms,
        )

        result_dict = response.model_dump()
        await _try_cache_context(query_str, filters, result_dict)

        return ApiResponse(
            success=True,
            message=(
                f"Context package built with {len(reranked)} source chunks "
                f"in {pipeline_ms:.0f} ms."
            ),
            data=result_dict,
        )

    except Exception as exc:
        logger.error("RAG context retrieval failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Context retrieval failed: {exc}",
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/rag/traceability
# ─────────────────────────────────────────────────────────────────────────────

@router.post(
    "/traceability",
    response_model=ApiResponse,
    summary="Retrieve traceability grounding package for story validation",
    description=(
        "Retrieves source chunks and requirements for a generated user story "
        "so Agent 4 can validate it against the original BRD. "
        "Results are cached for 15 minutes."
    ),
)
async def retrieve_traceability(request: TraceabilityRequest) -> ApiResponse:
    filters: dict[str, Any] = {
        "story_id": request.story_id,
        "requirement_ids": sorted(request.requirement_ids),
        "project_id": request.project_id,
        "document_id": request.document_id,
        "top_k": request.top_k,
    }

    # ── Cache hit ──────────────────────────────────────────────────────
    cached = await _try_get_cached_traceability(
        request.story_id, request.story_text, filters
    )
    if cached is not None:
        return ApiResponse(
            success=True,
            message="Traceability package retrieved (cached).",
            data=cached,
        )

    # ── Live retrieval ─────────────────────────────────────────────────
    try:
        t0 = time.perf_counter()

        # Build a combined query from story text + explicit requirement IDs
        req_str = " ".join(request.requirement_ids)
        query = f"{request.story_text} {req_str}".strip()

        # Hybrid retrieval scoped to project/document
        hybrid_result = await _get_hybrid_service().retrieve_by_query(
            query,
            project_id=request.project_id,
            document_id=request.document_id,
            bm25_top_k=request.top_k,
            dense_top_k=request.top_k,
        )

        # Fuse and rerank
        fused = _get_rrf_service().fuse(
            hybrid_result.bm25_results,
            hybrid_result.dense_results,
            top_k=request.top_k * 2,
        )
        reranked = await _get_reranker_service().rerank(
            query,
            fused,
            candidate_count=min(len(fused), request.top_k * 2),
            final_count=request.top_k,
        )

        retrieval_ms = (time.perf_counter() - t0) * 1000

        # Build the grounding package
        traceability = _get_context_builder().build_traceability_package(
            story_id=request.story_id,
            reranked_chunks=reranked,
            requirement_ids=request.requirement_ids,
            retrieval_latency_ms=retrieval_ms,
        )

        result_dict = traceability.model_dump()
        await _try_cache_traceability(
            request.story_id, request.story_text, filters, result_dict
        )

        return ApiResponse(
            success=True,
            message=(
                f"Traceability package built for story {request.story_id} "
                f"with {len(reranked)} source chunks in {retrieval_ms:.0f} ms."
            ),
            data=result_dict,
        )

    except Exception as exc:
        logger.error(
            "RAG traceability retrieval failed for story %s: %s",
            request.story_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Traceability retrieval failed: {exc}",
        ) from exc


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers  (silent-fail: a cache error must never break a live request)
# ─────────────────────────────────────────────────────────────────────────────

async def _try_get_cached_search(
    query: str, filters: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        from app.api.deps import get_redis
        return await get_cached_rag_search_result(get_redis(), query, filters)
    except Exception:
        return None


async def _try_cache_search(
    query: str, filters: dict[str, Any], data: dict[str, Any]
) -> None:
    try:
        from app.api.deps import get_redis
        await cache_rag_search_result(get_redis(), query, filters, data)
    except Exception:
        pass


async def _try_get_cached_context(
    query: str, filters: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        from app.api.deps import get_redis
        return await get_cached_rag_context_result(get_redis(), query, filters)
    except Exception:
        return None


async def _try_cache_context(
    query: str, filters: dict[str, Any], data: dict[str, Any]
) -> None:
    try:
        from app.api.deps import get_redis
        await cache_rag_context_result(get_redis(), query, filters, data)
    except Exception:
        pass


async def _try_get_cached_traceability(
    story_id: str, query: str, filters: dict[str, Any]
) -> dict[str, Any] | None:
    try:
        from app.api.deps import get_redis
        return await get_cached_rag_traceability_result(get_redis(), story_id, query, filters)
    except Exception:
        return None


async def _try_cache_traceability(
    story_id: str, query: str, filters: dict[str, Any], data: dict[str, Any]
) -> None:
    try:
        from app.api.deps import get_redis
        await cache_rag_traceability_result(get_redis(), story_id, query, filters, data)
    except Exception:
        pass
