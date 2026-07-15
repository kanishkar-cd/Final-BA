"""Redis caching helpers for hybrid global and user-scoped state.

Global keys are reserved for deterministic document preprocessing artifacts
keyed by document hash. Workflow, generation, validation, review, confidence,
iteration, and temporary AI state are always scoped by user.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis

from .cache_keys import (
    global_chunks,
    global_document,
    global_embeddings,
    global_metadata,
    global_parsed,
    rag_chunk_indexed,
    rag_context_result,
    rag_document_index_status,
    rag_project_index_status,
    rag_query_hash,
    rag_search_result,
    rag_traceability_result,
    stable_hash,
    user_ai_response,
    user_actors_current,
    user_business_goals_current,
    user_business_rules_current,
    user_confidence,
    user_constraints_current,
    user_dependencies_current,
    user_detailed_stories_current,
    user_detailed_story_versions,
    user_edge_cases_current,
    user_epics_current,
    user_features_current,
    user_functional_requirements_current,
    user_generation,
    user_generation_attempts,
    user_generation_latest_output,
    user_iteration,
    user_job_status,
    user_non_functional_requirements_current,
    user_one_line_story_artifacts_current,
    user_one_line_stories_current,
    user_one_line_story_versions,
    user_review,
    user_session,
    user_story_version_registry,
    user_validation_result,
    user_workflow,
)


class CacheTTL:
    """Default TTLs in seconds."""

    DOCUMENT = 60 * 60 * 24 * 30
    PARSED_DOCUMENT = 60 * 60 * 24 * 30
    DOCUMENT_CHUNKS = 60 * 60 * 24 * 30
    DOCUMENT_METADATA = 60 * 60 * 24 * 30
    DOCUMENT_EMBEDDINGS = 60 * 60 * 24 * 30
    USER_SESSION = 60 * 60 * 12
    WORKFLOW_STATE = 60 * 60 * 6
    GENERATION_ATTEMPTS = 60 * 60 * 6
    GENERATION_LATEST_OUTPUT = 60 * 60 * 6
    VALIDATION_RESULT = 60 * 60 * 6
    AI_RESPONSE = 60 * 60 * 6
    JOB_STATUS = 60 * 60 * 6
    ITERATION = 60 * 60 * 6
    CONFIDENCE = 60 * 60 * 6
    REVIEW = 60 * 60 * 24
    PLANNING_CURRENT = 60 * 60 * 24
    USER_STORY_CURRENT = 60 * 60 * 24
    USER_STORY_VERSIONS = None


@dataclass(frozen=True)
class GenerationAttempt:
    attempt_number: int
    output: dict[str, Any]
    confidence_score: float | None = None
    status: str = "generated"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class UserStoryVersion:
    story_id: str
    version: int
    payload: dict[str, Any]
    feedback: str | None = None
    approval_feedback: str | None = None
    approval_comments: str | None = None
    changed_by_user_id: str | None = None
    change_reason: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _json_loads(value: str | None) -> Any:
    return None if value is None else json.loads(value)


_FEEDBACK_FIELDS = {
    "feedback": None,
    "approval_feedback": None,
    "approval_comments": None,
}


def _with_feedback_fields(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**_FEEDBACK_FIELDS, **item} for item in items]


def _require_scope(user_id: str | None, scope_name: str = "user_id") -> str:
    if not user_id:
        raise ValueError(f"{scope_name} is required for user-scoped Redis cache access")
    return user_id


def _require_project(project_id: str | None) -> str:
    if not project_id:
        raise ValueError("project_id is required for user/project-scoped Redis cache access")
    return project_id


async def cache_document_hash_mapping(
    redis: Redis,
    document_hash: str,
    document_payload: dict[str, Any],
    ttl: int = CacheTTL.DOCUMENT,
) -> None:
    """Cache reusable document hash mapping and parser metadata globally."""
    await redis.set(global_document(document_hash), _json_dumps(document_payload), ex=ttl)


async def get_cached_document_hash_mapping(redis: Redis, document_hash: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(global_document(document_hash)))


async def cache_parsed_document(
    redis: Redis,
    document_hash: str,
    parsed_text: str,
    ttl: int = CacheTTL.PARSED_DOCUMENT,
) -> None:
    await redis.set(global_parsed(document_hash), parsed_text, ex=ttl)


async def get_cached_parsed_document(redis: Redis, document_hash: str) -> str | None:
    return await redis.get(global_parsed(document_hash))


async def cache_document_chunks(
    redis: Redis,
    document_hash: str,
    chunks: list[dict[str, Any]],
    ttl: int = CacheTTL.DOCUMENT_CHUNKS,
) -> None:
    await redis.set(global_chunks(document_hash), _json_dumps(chunks), ex=ttl)


async def get_cached_document_chunks(redis: Redis, document_hash: str) -> list[dict[str, Any]] | None:
    return _json_loads(await redis.get(global_chunks(document_hash)))


async def cache_document_embeddings(
    redis: Redis,
    document_hash: str,
    embeddings: list[dict[str, Any]],
    ttl: int = CacheTTL.DOCUMENT_EMBEDDINGS,
) -> None:
    await redis.set(global_embeddings(document_hash), _json_dumps(embeddings), ex=ttl)


async def get_cached_document_embeddings(redis: Redis, document_hash: str) -> list[dict[str, Any]] | None:
    return _json_loads(await redis.get(global_embeddings(document_hash)))


async def cache_document_metadata(
    redis: Redis,
    document_hash: str,
    metadata: dict[str, Any],
    ttl: int = CacheTTL.DOCUMENT_METADATA,
) -> None:
    await redis.set(global_metadata(document_hash), _json_dumps(metadata), ex=ttl)


async def get_cached_document_metadata(redis: Redis, document_hash: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(global_metadata(document_hash)))


async def cache_user_session(
    redis: Redis,
    user_id: str,
    session: dict[str, Any],
    ttl: int = CacheTTL.USER_SESSION,
) -> None:
    await redis.set(user_session(_require_scope(user_id)), _json_dumps(session), ex=ttl)


async def get_cached_user_session(redis: Redis, user_id: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(user_session(_require_scope(user_id))))


async def invalidate_user_session(redis: Redis, user_id: str) -> int:
    return await redis.delete(user_session(_require_scope(user_id)))


async def cache_project_summary(
    redis: Redis,
    user_id: str,
    project_id: str,
    summary: dict[str, Any],
    ttl: int = CacheTTL.WORKFLOW_STATE,
) -> None:
    await redis.set(user_workflow(_require_scope(user_id), _require_project(project_id)), _json_dumps(summary), ex=ttl)


async def get_cached_project_summary(redis: Redis, user_id: str, project_id: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(user_workflow(_require_scope(user_id), _require_project(project_id))))


async def cache_workflow_state(
    redis: Redis,
    user_id: str,
    project_id: str,
    workflow: dict[str, Any],
    ttl: int = CacheTTL.WORKFLOW_STATE,
) -> None:
    await cache_project_summary(redis, user_id, project_id, workflow, ttl)


async def get_cached_workflow_state(redis: Redis, user_id: str, project_id: str) -> dict[str, Any] | None:
    return await get_cached_project_summary(redis, user_id, project_id)


async def append_generation_attempt(
    redis: Redis,
    user_id: str,
    project_id: str,
    job_id: str,
    attempt: GenerationAttempt,
    ttl: int = CacheTTL.GENERATION_ATTEMPTS,
) -> None:
    """Append a temporary generation attempt and refresh the latest output key."""
    user_id = _require_scope(user_id)
    project_id = _require_project(project_id)
    attempts_key = user_generation_attempts(user_id, project_id, job_id)
    latest_key = user_generation_latest_output(user_id, project_id, job_id)
    serialized_attempt = _json_dumps(asdict(attempt))

    async with redis.pipeline(transaction=True) as pipe:
        pipe.rpush(attempts_key, serialized_attempt)
        pipe.expire(attempts_key, ttl)
        pipe.set(latest_key, _json_dumps(attempt.output), ex=CacheTTL.GENERATION_LATEST_OUTPUT)
        await pipe.execute()


async def get_generation_attempts(redis: Redis, user_id: str, project_id: str, job_id: str) -> list[dict[str, Any]]:
    items = await redis.lrange(
        user_generation_attempts(_require_scope(user_id), _require_project(project_id), job_id),
        0,
        -1,
    )
    return [json.loads(item) for item in items]


async def get_latest_generation_output(redis: Redis, user_id: str, project_id: str, job_id: str) -> dict[str, Any] | None:
    return _json_loads(
        await redis.get(user_generation_latest_output(_require_scope(user_id), _require_project(project_id), job_id))
    )


async def cache_generation_state(
    redis: Redis,
    user_id: str,
    project_id: str,
    generation: dict[str, Any],
    ttl: int = CacheTTL.GENERATION_LATEST_OUTPUT,
) -> None:
    await redis.set(user_generation(_require_scope(user_id), _require_project(project_id)), _json_dumps(generation), ex=ttl)


async def get_cached_generation_state(redis: Redis, user_id: str, project_id: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(user_generation(_require_scope(user_id), _require_project(project_id))))


async def cache_validation_result(
    redis: Redis,
    user_id: str,
    project_id: str,
    job_id: str,
    result: dict[str, Any],
    ttl: int = CacheTTL.VALIDATION_RESULT,
) -> None:
    await redis.set(
        user_validation_result(_require_scope(user_id), _require_project(project_id), job_id),
        _json_dumps(result),
        ex=ttl,
    )


async def get_cached_validation_result(redis: Redis, user_id: str, project_id: str, job_id: str) -> dict[str, Any] | None:
    return _json_loads(
        await redis.get(user_validation_result(_require_scope(user_id), _require_project(project_id), job_id))
    )


async def cache_ai_response(
    redis: Redis,
    user_id: str,
    project_id: str,
    prompt_payload: dict[str, Any],
    response_payload: dict[str, Any],
    ttl: int = CacheTTL.AI_RESPONSE,
) -> str:
    cache_hash = stable_hash(prompt_payload)
    await redis.set(
        user_ai_response(_require_scope(user_id), _require_project(project_id), cache_hash),
        _json_dumps(response_payload),
        ex=ttl,
    )
    return cache_hash


async def get_cached_ai_response(
    redis: Redis,
    user_id: str,
    project_id: str,
    prompt_payload: dict[str, Any],
) -> dict[str, Any] | None:
    cache_hash = stable_hash(prompt_payload)
    return _json_loads(await redis.get(user_ai_response(_require_scope(user_id), _require_project(project_id), cache_hash)))


async def cache_iteration_state(
    redis: Redis,
    user_id: str,
    project_id: str,
    iteration: dict[str, Any],
    ttl: int = CacheTTL.ITERATION,
) -> None:
    await redis.set(user_iteration(_require_scope(user_id), _require_project(project_id)), _json_dumps(iteration), ex=ttl)


async def get_cached_iteration_state(redis: Redis, user_id: str, project_id: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(user_iteration(_require_scope(user_id), _require_project(project_id))))


async def cache_confidence_score(
    redis: Redis,
    user_id: str,
    project_id: str,
    confidence: dict[str, Any],
    ttl: int = CacheTTL.CONFIDENCE,
) -> None:
    await redis.set(user_confidence(_require_scope(user_id), _require_project(project_id)), _json_dumps(confidence), ex=ttl)


async def get_cached_confidence_score(redis: Redis, user_id: str, project_id: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(user_confidence(_require_scope(user_id), _require_project(project_id))))


async def cache_review_state(
    redis: Redis,
    user_id: str,
    project_id: str,
    review: dict[str, Any],
    ttl: int = CacheTTL.REVIEW,
) -> None:
    await redis.set(user_review(_require_scope(user_id), _require_project(project_id)), _json_dumps(review), ex=ttl)


async def get_cached_review_state(redis: Redis, user_id: str, project_id: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(user_review(_require_scope(user_id), _require_project(project_id))))


async def _cache_project_artifact_list(
    redis: Redis,
    key: str,
    artifacts: list[dict[str, Any]],
    ttl: int,
) -> None:
    await redis.set(key, _json_dumps(artifacts), ex=ttl)


async def _get_cached_project_artifact_list(redis: Redis, key: str) -> list[dict[str, Any]] | None:
    return _json_loads(await redis.get(key))


async def cache_actors(
    redis: Redis,
    user_id: str,
    project_id: str,
    actors: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_actors_current(_require_scope(user_id), _require_project(project_id)),
        actors,
        ttl,
    )


async def get_cached_actors(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_actors_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_functional_requirements(
    redis: Redis,
    user_id: str,
    project_id: str,
    requirements: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_functional_requirements_current(_require_scope(user_id), _require_project(project_id)),
        requirements,
        ttl,
    )


async def get_cached_functional_requirements(
    redis: Redis,
    user_id: str,
    project_id: str,
) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_functional_requirements_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_non_functional_requirements(
    redis: Redis,
    user_id: str,
    project_id: str,
    requirements: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_non_functional_requirements_current(_require_scope(user_id), _require_project(project_id)),
        requirements,
        ttl,
    )


async def get_cached_non_functional_requirements(
    redis: Redis,
    user_id: str,
    project_id: str,
) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_non_functional_requirements_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_business_rules(
    redis: Redis,
    user_id: str,
    project_id: str,
    business_rules: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_business_rules_current(_require_scope(user_id), _require_project(project_id)),
        business_rules,
        ttl,
    )


async def get_cached_business_rules(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_business_rules_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_business_goals(
    redis: Redis,
    user_id: str,
    project_id: str,
    business_goals: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_business_goals_current(_require_scope(user_id), _require_project(project_id)),
        business_goals,
        ttl,
    )


async def get_cached_business_goals(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_business_goals_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_edge_cases(
    redis: Redis,
    user_id: str,
    project_id: str,
    edge_cases: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_edge_cases_current(_require_scope(user_id), _require_project(project_id)),
        edge_cases,
        ttl,
    )


async def get_cached_edge_cases(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_edge_cases_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_constraints(
    redis: Redis,
    user_id: str,
    project_id: str,
    constraints: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_constraints_current(_require_scope(user_id), _require_project(project_id)),
        constraints,
        ttl,
    )


async def get_cached_constraints(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_constraints_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_dependencies(
    redis: Redis,
    user_id: str,
    project_id: str,
    dependencies: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_dependencies_current(_require_scope(user_id), _require_project(project_id)),
        dependencies,
        ttl,
    )


async def get_cached_dependencies(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_dependencies_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_epics(
    redis: Redis,
    user_id: str,
    project_id: str,
    epics: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_epics_current(_require_scope(user_id), _require_project(project_id)),
        _with_feedback_fields(epics),
        ttl,
    )


async def get_cached_epics(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_epics_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_features(
    redis: Redis,
    user_id: str,
    project_id: str,
    features: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_features_current(_require_scope(user_id), _require_project(project_id)),
        _with_feedback_fields(features),
        ttl,
    )


async def get_cached_features(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_features_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_one_line_story_artifacts(
    redis: Redis,
    user_id: str,
    project_id: str,
    one_line_stories: list[dict[str, Any]],
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    await _cache_project_artifact_list(
        redis,
        user_one_line_story_artifacts_current(_require_scope(user_id), _require_project(project_id)),
        _with_feedback_fields(one_line_stories),
        ttl,
    )


async def get_cached_one_line_story_artifacts(
    redis: Redis,
    user_id: str,
    project_id: str,
) -> list[dict[str, Any]] | None:
    return await _get_cached_project_artifact_list(
        redis,
        user_one_line_story_artifacts_current(_require_scope(user_id), _require_project(project_id)),
    )


async def cache_planning_artifacts(
    redis: Redis,
    user_id: str,
    project_id: str,
    *,
    actors: list[dict[str, Any]] | None = None,
    functional_requirements: list[dict[str, Any]] | None = None,
    non_functional_requirements: list[dict[str, Any]] | None = None,
    business_rules: list[dict[str, Any]] | None = None,
    business_goals: list[dict[str, Any]] | None = None,
    edge_cases: list[dict[str, Any]] | None = None,
    constraints: list[dict[str, Any]] | None = None,
    dependencies: list[dict[str, Any]] | None = None,
    epics: list[dict[str, Any]] | None = None,
    features: list[dict[str, Any]] | None = None,
    one_line_stories: list[dict[str, Any]] | None = None,
    ttl: int = CacheTTL.PLANNING_CURRENT,
) -> None:
    """Refresh current approved planning artifacts after PostgreSQL commit."""
    user_id = _require_scope(user_id)
    project_id = _require_project(project_id)

    async with redis.pipeline(transaction=True) as pipe:
        if actors is not None:
            pipe.set(user_actors_current(user_id, project_id), _json_dumps(actors), ex=ttl)
        if functional_requirements is not None:
            pipe.set(
                user_functional_requirements_current(user_id, project_id),
                _json_dumps(functional_requirements),
                ex=ttl,
            )
        if non_functional_requirements is not None:
            pipe.set(
                user_non_functional_requirements_current(user_id, project_id),
                _json_dumps(non_functional_requirements),
                ex=ttl,
            )
        if business_rules is not None:
            pipe.set(user_business_rules_current(user_id, project_id), _json_dumps(business_rules), ex=ttl)
        if business_goals is not None:
            pipe.set(user_business_goals_current(user_id, project_id), _json_dumps(business_goals), ex=ttl)
        if edge_cases is not None:
            pipe.set(user_edge_cases_current(user_id, project_id), _json_dumps(edge_cases), ex=ttl)
        if constraints is not None:
            pipe.set(user_constraints_current(user_id, project_id), _json_dumps(constraints), ex=ttl)
        if dependencies is not None:
            pipe.set(user_dependencies_current(user_id, project_id), _json_dumps(dependencies), ex=ttl)
        if epics is not None:
            pipe.set(user_epics_current(user_id, project_id), _json_dumps(_with_feedback_fields(epics)), ex=ttl)
        if features is not None:
            pipe.set(user_features_current(user_id, project_id), _json_dumps(_with_feedback_fields(features)), ex=ttl)
        if one_line_stories is not None:
            pipe.set(
                user_one_line_story_artifacts_current(user_id, project_id),
                _json_dumps(_with_feedback_fields(one_line_stories)),
                ex=ttl,
            )
        await pipe.execute()


async def cache_one_line_user_stories(
    redis: Redis,
    user_id: str,
    project_id: str,
    stories: list[dict[str, Any]],
    ttl: int = CacheTTL.USER_STORY_CURRENT,
) -> None:
    await redis.set(
        user_one_line_stories_current(_require_scope(user_id), _require_project(project_id)),
        _json_dumps(_with_feedback_fields(stories)),
        ex=ttl,
    )


async def get_cached_one_line_user_stories(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return _json_loads(
        await redis.get(user_one_line_stories_current(_require_scope(user_id), _require_project(project_id)))
    )


async def cache_detailed_user_stories(
    redis: Redis,
    user_id: str,
    project_id: str,
    stories: list[dict[str, Any]],
    ttl: int = CacheTTL.USER_STORY_CURRENT,
) -> None:
    await redis.set(
        user_detailed_stories_current(_require_scope(user_id), _require_project(project_id)),
        _json_dumps(_with_feedback_fields(stories)),
        ex=ttl,
    )


async def get_cached_detailed_user_stories(redis: Redis, user_id: str, project_id: str) -> list[dict[str, Any]] | None:
    return _json_loads(
        await redis.get(user_detailed_stories_current(_require_scope(user_id), _require_project(project_id)))
    )


async def append_one_line_user_story_version(
    redis: Redis,
    user_id: str,
    project_id: str,
    version: UserStoryVersion,
    ttl: int | None = CacheTTL.USER_STORY_VERSIONS,
) -> None:
    user_id = _require_scope(user_id)
    project_id = _require_project(project_id)
    version_key = user_one_line_story_versions(user_id, project_id, version.story_id)
    registry_key = user_story_version_registry(user_id, project_id)

    async with redis.pipeline(transaction=True) as pipe:
        pipe.rpush(version_key, _json_dumps(asdict(version)))
        pipe.sadd(registry_key, version_key)
        if ttl is not None:
            pipe.expire(version_key, ttl)
            pipe.expire(registry_key, ttl)
        await pipe.execute()


async def get_one_line_user_story_versions(
    redis: Redis,
    user_id: str,
    project_id: str,
    story_id: str,
) -> list[dict[str, Any]]:
    items = await redis.lrange(
        user_one_line_story_versions(_require_scope(user_id), _require_project(project_id), story_id),
        0,
        -1,
    )
    return [json.loads(item) for item in items]


async def append_detailed_user_story_version(
    redis: Redis,
    user_id: str,
    project_id: str,
    version: UserStoryVersion,
    ttl: int | None = CacheTTL.USER_STORY_VERSIONS,
) -> None:
    user_id = _require_scope(user_id)
    project_id = _require_project(project_id)
    version_key = user_detailed_story_versions(user_id, project_id, version.story_id)
    registry_key = user_story_version_registry(user_id, project_id)

    async with redis.pipeline(transaction=True) as pipe:
        pipe.rpush(version_key, _json_dumps(asdict(version)))
        pipe.sadd(registry_key, version_key)
        if ttl is not None:
            pipe.expire(version_key, ttl)
            pipe.expire(registry_key, ttl)
        await pipe.execute()


async def get_detailed_user_story_versions(
    redis: Redis,
    user_id: str,
    project_id: str,
    story_id: str,
) -> list[dict[str, Any]]:
    items = await redis.lrange(
        user_detailed_story_versions(_require_scope(user_id), _require_project(project_id), story_id),
        0,
        -1,
    )
    return [json.loads(item) for item in items]


async def set_job_status(
    redis: Redis,
    user_id: str,
    job_id: str,
    status: str,
    details: dict[str, Any] | None = None,
    ttl: int = CacheTTL.JOB_STATUS,
) -> None:
    payload = {
        "job_id": job_id,
        "status": status,
        "details": details or {},
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await redis.set(user_job_status(_require_scope(user_id), job_id), _json_dumps(payload), ex=ttl)


async def get_job_status(redis: Redis, user_id: str, job_id: str) -> dict[str, Any] | None:
    return _json_loads(await redis.get(user_job_status(_require_scope(user_id), job_id)))


async def invalidate_document_cache(redis: Redis, document_hash: str) -> int:
    """Invalidate global preprocessing cache after parser changes or source deletion."""
    return await redis.delete(
        global_document(document_hash),
        global_parsed(document_hash),
        global_chunks(document_hash),
        global_embeddings(document_hash),
        global_metadata(document_hash),
    )


async def invalidate_generation_cache(redis: Redis, user_id: str, project_id: str, job_id: str) -> int:
    """Remove temporary attempts after approval/rejection has been committed."""
    user_id = _require_scope(user_id)
    project_id = _require_project(project_id)
    return await redis.delete(
        user_generation_attempts(user_id, project_id, job_id),
        user_generation_latest_output(user_id, project_id, job_id),
        user_validation_result(user_id, project_id, job_id),
        user_job_status(user_id, job_id),
    )


async def invalidate_project_cache(redis: Redis, user_id: str, project_id: str) -> int:
    """Invalidate user-scoped project workflow state after approvals or exports change."""
    user_id = _require_scope(user_id)
    project_id = _require_project(project_id)
    return await redis.delete(
        user_workflow(user_id, project_id),
        user_generation(user_id, project_id),
        user_iteration(user_id, project_id),
        user_confidence(user_id, project_id),
        user_review(user_id, project_id),
        user_actors_current(user_id, project_id),
        user_functional_requirements_current(user_id, project_id),
        user_non_functional_requirements_current(user_id, project_id),
        user_business_rules_current(user_id, project_id),
        user_business_goals_current(user_id, project_id),
        user_edge_cases_current(user_id, project_id),
        user_constraints_current(user_id, project_id),
        user_dependencies_current(user_id, project_id),
        user_epics_current(user_id, project_id),
        user_features_current(user_id, project_id),
        user_one_line_story_artifacts_current(user_id, project_id),
        user_one_line_stories_current(user_id, project_id),
        user_detailed_stories_current(user_id, project_id),
    )


async def invalidate_user_story_version_history(redis: Redis, user_id: str, project_id: str) -> int:
    """Remove story rollback history when the owning project or document is purged."""
    user_id = _require_scope(user_id)
    project_id = _require_project(project_id)
    story_registry_key = user_story_version_registry(user_id, project_id)
    story_version_keys = await redis.smembers(story_registry_key)
    return await redis.delete(
        story_registry_key,
        *story_version_keys,
    )


# ──────────────────────────────────────────────────────────────────────────────
# RAG query result caching helpers
#
# Search and context results are expensive (embedding + Qdrant + reranking).
# They are cached globally by a stable hash of the query + filters so the
# same request from any user hits the cache on the second call.
#
# TTLs are kept short (15 minutes) because document indexes can change.
# ──────────────────────────────────────────────────────────────────────────────

class RAGCacheTTL:
    """TTLs (seconds) for RAG layer cache entries."""

    SEARCH_RESULT = 60 * 15        # 15 minutes
    CONTEXT_RESULT = 60 * 15       # 15 minutes
    TRACEABILITY_RESULT = 60 * 15  # 15 minutes
    CHUNK_INDEXED_FLAG = 60 * 60 * 24 * 30   # 30 days (mirrors embedding cache)
    INDEX_STATUS = 60 * 60 * 24    # 24 hours


async def cache_rag_search_result(
    redis: Redis,
    query: str,
    filters: dict[str, Any],
    result: dict[str, Any],
    ttl: int = RAGCacheTTL.SEARCH_RESULT,
) -> str:
    """Cache a hybrid search result and return the query hash."""
    key = rag_search_result(rag_query_hash(query, filters))
    await redis.set(key, _json_dumps(result), ex=ttl)
    return key


async def get_cached_rag_search_result(
    redis: Redis,
    query: str,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    key = rag_search_result(rag_query_hash(query, filters))
    return _json_loads(await redis.get(key))


async def cache_rag_context_result(
    redis: Redis,
    query: str,
    filters: dict[str, Any],
    result: dict[str, Any],
    ttl: int = RAGCacheTTL.CONTEXT_RESULT,
) -> str:
    """Cache a context package and return the query hash."""
    key = rag_context_result(rag_query_hash(query, filters))
    await redis.set(key, _json_dumps(result), ex=ttl)
    return key


async def get_cached_rag_context_result(
    redis: Redis,
    query: str,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    key = rag_context_result(rag_query_hash(query, filters))
    return _json_loads(await redis.get(key))


async def cache_rag_traceability_result(
    redis: Redis,
    story_id: str,
    query: str,
    filters: dict[str, Any],
    result: dict[str, Any],
    ttl: int = RAGCacheTTL.TRACEABILITY_RESULT,
) -> str:
    """Cache a traceability grounding package and return the cache key."""
    key = rag_traceability_result(story_id, rag_query_hash(query, filters))
    await redis.set(key, _json_dumps(result), ex=ttl)
    return key


async def get_cached_rag_traceability_result(
    redis: Redis,
    story_id: str,
    query: str,
    filters: dict[str, Any],
) -> dict[str, Any] | None:
    key = rag_traceability_result(story_id, rag_query_hash(query, filters))
    return _json_loads(await redis.get(key))


async def mark_chunk_indexed(
    redis: Redis,
    chunk_id: str,
    ttl: int = RAGCacheTTL.CHUNK_INDEXED_FLAG,
) -> None:
    """Set a flag indicating this chunk has been embedded and stored in Qdrant."""
    await redis.set(rag_chunk_indexed(chunk_id), "1", ex=ttl)


async def is_chunk_indexed(redis: Redis, chunk_id: str) -> bool:
    """Return True if the chunk has a live indexed flag in Redis."""
    return await redis.exists(rag_chunk_indexed(chunk_id)) == 1


async def invalidate_rag_chunk(redis: Redis, chunk_id: str) -> int:
    """Remove the indexed flag when a chunk is deleted or re-indexed."""
    return await redis.delete(rag_chunk_indexed(chunk_id))


async def set_document_index_status(
    redis: Redis,
    document_id: str,
    status: dict[str, Any],
    ttl: int = RAGCacheTTL.INDEX_STATUS,
) -> None:
    """Store a summary of how many chunks in a document have been indexed."""
    await redis.set(rag_document_index_status(document_id), _json_dumps(status), ex=ttl)


async def get_document_index_status(
    redis: Redis, document_id: str
) -> dict[str, Any] | None:
    return _json_loads(await redis.get(rag_document_index_status(document_id)))


async def set_project_index_status(
    redis: Redis,
    project_id: str,
    status: dict[str, Any],
    ttl: int = RAGCacheTTL.INDEX_STATUS,
) -> None:
    """Store a summary of indexing progress across a whole project."""
    await redis.set(rag_project_index_status(project_id), _json_dumps(status), ex=ttl)


async def get_project_index_status(
    redis: Redis, project_id: str
) -> dict[str, Any] | None:
    return _json_loads(await redis.get(rag_project_index_status(project_id)))


async def invalidate_rag_document_cache(redis: Redis, document_id: str) -> int:
    """Remove indexing status and any search caches for a document."""
    return await redis.delete(rag_document_index_status(document_id))
