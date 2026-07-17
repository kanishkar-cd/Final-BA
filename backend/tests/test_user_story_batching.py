from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.token_budget import count_tokens
from app.agents.user_story_agent import UserStoryGenerationAgent
from app.schemas.user_story import (
    Agent1Output,
    GenerateUserStoriesRequest,
    OneLineStoryInput,
    PlanningArtifact,
    RetrievedChunk,
    TraceabilityLink,
    UserStory,
    ValidateUserStoriesRequest,
)
from app.validations.story_validator import UserStoryValidator


def _large_request(feature_count: int = 6) -> GenerateUserStoriesRequest:
    chunks = [
        RetrievedChunk(
            id=f"CHUNK-{index}",
            content=(
                f"Persona {index} supplies input {index}; the system returns observable output "
                f"{index} and rejects invalid input {index}."
            ),
        )
        for index in range(1, feature_count + 1)
    ]
    requirements = [
        PlanningArtifact(
            id=f"FR-{index:03d}",
            name=f"Complete capability {index}",
            metadata={"actor": f"Persona {index}", "chunk_refs": [f"CHUNK-{index}"]},
        )
        for index in range(1, feature_count + 1)
    ]
    epics = [PlanningArtifact(id="EPIC-1", name="Large workflow")]
    features = [
        PlanningArtifact(id=f"FEAT-{index}", name=f"Capability {index}")
        for index in range(1, feature_count + 1)
    ]
    stories = [
        OneLineStoryInput(
            id=f"OLS-{index}",
            feature_id=f"FEAT-{index}",
            epic_id="EPIC-1",
            summary=f"Complete capability {index}",
            chunk_refs=[f"CHUNK-{index}"],
            requirement_refs=[f"FR-{index:03d}"],
            actor=f"Persona {index}",
        )
        for index in range(1, feature_count + 1)
    ]
    matrix = [
        {
            "feature_id": f"FEAT-{index}",
            "one_line_story_id": f"OLS-{index}",
            "chunk_ids": [f"CHUNK-{index}"],
            "requirement_ids": [f"FR-{index:03d}"],
        }
        for index in range(1, feature_count + 1)
    ]
    agent1 = Agent1Output(
        chunks=chunks,
        actors=[f"Persona {index}" for index in range(1, feature_count + 1)],
        functional_requirements=requirements,
    )
    return GenerateUserStoriesRequest(
        workflow_id="WF-LARGE-BATCH",
        retrieved_chunks=chunks,
        agent1_output=agent1,
        epics=epics,
        features=features,
        one_line_stories=stories,
        traceability={"traceability_matrix": matrix},
    )


@pytest.mark.asyncio
async def test_large_multi_feature_request_is_split_into_budgeted_calls(monkeypatch) -> None:
    monkeypatch.setenv("USER_STORY_BATCH_TOKEN_BUDGET", "9600")
    monkeypatch.setenv("USER_STORY_BATCH_MAX_STORIES", "2")
    calls: list[tuple[int, int]] = []

    async def executor(system_prompt, user_prompt, payload):
        calls.append((
            len(payload.features),
            count_tokens(system_prompt) + count_tokens(user_prompt)
            + UserStoryGenerationAgent._output_token_allowance(len(payload.features)),
        ))
        return []

    await UserStoryGenerationAgent(agent_executor=executor).execute(_large_request())

    assert len(calls) >= 3
    assert sum(size for size, _ in calls) == 6
    assert all(size <= 2 for size, _ in calls)
    assert all(tokens <= 9600 for _, tokens in calls)


@pytest.mark.asyncio
async def test_too_large_batch_retry_recursively_uses_smaller_payload(monkeypatch) -> None:
    monkeypatch.setenv("USER_STORY_BATCH_TOKEN_BUDGET", "50000")
    monkeypatch.setenv("USER_STORY_BATCH_MAX_STORIES", "4")
    call_sizes: list[int] = []

    async def executor(system_prompt, user_prompt, payload):
        call_sizes.append(len(payload.features))
        if len(call_sizes) == 1:
            raise RuntimeError("413 Request too large: requested tokens exceed limit")
        return []

    await UserStoryGenerationAgent(agent_executor=executor).execute(_large_request(4))

    assert call_sizes == [4, 2, 2]
    assert all(size < call_sizes[0] for size in call_sizes[1:])


def test_infrastructure_story_without_actor_mapping_is_flagged() -> None:
    story = UserStory(
        id="US-001",
        feature_id="FEAT-CLOUD",
        epic_id="EPIC-INFRA",
        one_line_story_id="OLS-CLOUD",
        title="Cloud-based hosting",
        user_story="As a Merchant, I want cloud-based hosting, so that services remain available.",
        description="Deploy the backend to managed cloud infrastructure.",
        persona="Merchant",
        goal="cloud-based hosting",
        traceability=TraceabilityLink(
            workflow_id="WF-INFRA",
            feature_refs=["FEAT-CLOUD"],
            epic_refs=["EPIC-INFRA"],
            one_line_story_refs=["OLS-CLOUD"],
        ),
    )
    result = UserStoryValidator().validate(ValidateUserStoriesRequest(
        workflow_id="WF-INFRA",
        generated_user_stories=[story],
        traceability={
            "actor_requirement_mappings": [
                {"actor": "Merchant", "requirement": "Upload and manage products"},
                {"actor": "Buyer", "requirement": "Search and purchase products"},
            ]
        },
    ))

    assert any(
        issue.category == "Persona Correctness"
        and "no supporting actor-to-requirement mapping" in issue.message
        for issue in result.issues
    )
