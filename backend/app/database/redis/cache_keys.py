"""
Redis cache key definitions for the BA Accelerator.

Namespace Strategy
────────────────────────────────────────────────────────────

GLOBAL CACHE
------------
global:* keys contain deterministic preprocessing artifacts
that can be shared across users.

Examples:
    global:document:{hash}
    global:chunks:{hash}

USER CACHE
----------
user:{user_id}:* keys contain user/project specific data and
must never be shared across users.

Examples:
    user:123:project:456:workflow
    user:123:project:456:stories

RAG CACHE
---------
rag:* keys contain retrieval/indexing cache entries.

Examples:
    rag:search:{query_hash}
    rag:indexed:chunk:{chunk_id}
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


# =============================================================================
# GLOBAL CACHE KEYS
# =============================================================================

def global_document(document_hash: str) -> str:
    return f"global:document:{document_hash}"


def global_parsed(document_hash: str) -> str:
    return f"global:parsed:{document_hash}"


def global_chunks(document_hash: str) -> str:
    return f"global:chunks:{document_hash}"


def global_embeddings(document_hash: str) -> str:
    return f"global:embeddings:{document_hash}"


def global_metadata(document_hash: str) -> str:
    return f"global:metadata:{document_hash}"


# =============================================================================
# USER WORKFLOW CACHE KEYS
# =============================================================================

def user_session(user_id: str) -> str:
    return f"user:{user_id}:session"


def user_workflow(user_id: str, project_id: str) -> str:
    return f"user:{user_id}:project:{project_id}:workflow"


def user_generation(user_id: str, project_id: str) -> str:
    return f"user:{user_id}:project:{project_id}:generation"


def user_iteration(user_id: str, project_id: str) -> str:
    return f"user:{user_id}:project:{project_id}:iteration"


def user_confidence(user_id: str, project_id: str) -> str:
    return f"user:{user_id}:project:{project_id}:confidence"


def user_review(user_id: str, project_id: str) -> str:
    return f"user:{user_id}:project:{project_id}:review"


# =============================================================================
# PLANNING CACHE KEYS (AGENT 1 + AGENT 2)
# =============================================================================

def user_planning_cache(user_id: str, project_id: str) -> str:
    return f"user:{user_id}:project:{project_id}:planning"


def user_actors_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:actors:current"


def user_functional_requirements_current(user_id: str, project_id: str) -> str:
    return (
        f"{user_planning_cache(user_id, project_id)}:"
        f"functional_requirements:current"
    )


def user_non_functional_requirements_current(
    user_id: str,
    project_id: str,
) -> str:
    return (
        f"{user_planning_cache(user_id, project_id)}:"
        f"non_functional_requirements:current"
    )


def user_business_rules_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:business_rules:current"


def user_business_goals_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:business_goals:current"


def user_edge_cases_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:edge_cases:current"


def user_constraints_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:constraints:current"


def user_dependencies_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:dependencies:current"


def user_epics_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:epics:current"


def user_features_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:features:current"


def user_one_line_story_artifacts_current(
    user_id: str,
    project_id: str,
) -> str:
    return (
        f"{user_planning_cache(user_id, project_id)}:"
        f"one_line_stories:current"
    )


# =============================================================================
# STORY CACHE KEYS (AGENT 3)
# =============================================================================

def user_story_cache(user_id: str, project_id: str) -> str:
    return f"user:{user_id}:project:{project_id}:stories"


def user_planning_cache(user_id: str, project_id: str) -> str:
    return f"user:{user_id}:project:{project_id}:planning"


def user_actors_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:actors:current"


def user_functional_requirements_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:functional_requirements:current"


def user_non_functional_requirements_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:non_functional_requirements:current"


def user_business_rules_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:business_rules:current"


def user_business_goals_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:business_goals:current"


def user_edge_cases_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:edge_cases:current"


def user_constraints_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:constraints:current"


def user_dependencies_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:dependencies:current"


def user_epics_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:epics:current"


def user_features_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:features:current"


def user_one_line_story_artifacts_current(user_id: str, project_id: str) -> str:
    return f"{user_planning_cache(user_id, project_id)}:one_line_stories:current"


def user_story_version_registry(user_id: str, project_id: str) -> str:
    return f"{user_story_cache(user_id, project_id)}:version_keys"


def user_one_line_stories_current(user_id: str, project_id: str) -> str:
    return f"{user_story_cache(user_id, project_id)}:one_line:current"


def user_one_line_story_versions(
    user_id: str,
    project_id: str,
    story_id: str,
) -> str:
    return (
        f"{user_story_cache(user_id, project_id)}:"
        f"one_line:{story_id}:versions"
    )


def user_detailed_stories_current(user_id: str, project_id: str) -> str:
    return f"{user_story_cache(user_id, project_id)}:detailed:current"


def user_detailed_story_versions(
    user_id: str,
    project_id: str,
    story_id: str,
) -> str:
    return (
        f"{user_story_cache(user_id, project_id)}:"
        f"detailed:{story_id}:versions"
    )


# =============================================================================
# JOB / EXECUTION CACHE KEYS
# =============================================================================

def user_job(user_id: str, job_id: str) -> str:
    return f"user:{user_id}:job:{job_id}"


def user_job_status(user_id: str, job_id: str) -> str:
    return f"{user_job(user_id, job_id)}:status"


def user_generation_attempts(
    user_id: str,
    project_id: str,
    job_id: str,
) -> str:
    return (
        f"{user_generation(user_id, project_id)}:"
        f"job:{job_id}:attempts"
    )


def user_generation_latest_output(
    user_id: str,
    project_id: str,
    job_id: str,
) -> str:
    return (
        f"{user_generation(user_id, project_id)}:"
        f"job:{job_id}:latest_output"
    )


def user_validation_result(
    user_id: str,
    project_id: str,
    job_id: str,
) -> str:
    return (
        f"{user_generation(user_id, project_id)}:"
        f"job:{job_id}:validation"
    )


def user_ai_response(
    user_id: str,
    project_id: str,
    cache_hash: str,
) -> str:
    return (
        f"{user_generation(user_id, project_id)}:"
        f"ai_response:{cache_hash}"
    )


# =============================================================================
# RAG CACHE KEYS
# =============================================================================

def rag_search_result(query_hash: str) -> str:
    """
    Cached hybrid retrieval result.
    (BM25 + Dense + Fusion)
    """
    return f"rag:search:{query_hash}"


def rag_context_result(query_hash: str) -> str:
    """
    Cached final context package returned
    by the retrieval pipeline.
    """
    return f"rag:context:{query_hash}"


def rag_traceability_result(
    story_id: str,
    query_hash: str,
) -> str:
    """
    Cached traceability package used
    for story grounding.
    """
    return f"rag:traceability:{story_id}:{query_hash}"


def rag_chunk_indexed(chunk_id: str) -> str:
    """
    Flag indicating a chunk has already
    been embedded and indexed.
    """
    return f"rag:indexed:chunk:{chunk_id}"


def rag_document_index_status(document_id: str) -> str:
    """
    Indexing status of a document.
    """
    return f"rag:indexed:document:{document_id}"


def rag_project_index_status(project_id: str) -> str:
    """
    Indexing status of a project.
    """
    return f"rag:indexed:project:{project_id}"


def rag_query_hash(query: str, filters: Any) -> str:
    """
    Stable query hash used by RAG cache.
    """
    payload = {
        "query": query,
        "filters": filters,
    }
    return stable_hash(payload)


# =============================================================================
# UTILITIES
# =============================================================================

def stable_hash(payload: Any) -> str:
    """
    Generate deterministic SHA-256 hash
    for cache payloads.

    Used for:
        - AI response cache
        - Prompt cache
        - Model parameter cache
        - RAG query cache
    """
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()