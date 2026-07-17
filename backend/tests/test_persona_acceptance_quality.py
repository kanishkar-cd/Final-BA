from __future__ import annotations

import asyncio
import re

from app.agents.epic_agent_2 import Epic, EpicGenerationOutput
from app.agents.requirement_analysis_agent import (
    ActorRequirementMapping,
    RequirementAnalysisOutput,
)
from app.agents.user_story_agent import UserStoryGenerationAgent
from app.orchestrator.langgraph_adapters import (
    EpicFeatureAdapter,
    EpicOneLineStoryAdapter,
    WorkflowStateAdapter,
)
from app.schemas.user_story import AcceptanceCriterion, RetrievedChunk
from app.validations.story_validator import UserStoryValidator


TWO_PERSONA_BRD = """
Merchant Use Cases
The Merchant can add catalog inventory with a unique SKU and price.
The system rejects a duplicate SKU and reports the existing item.

Buyer Use Cases
The Buyer can search the catalog by product name and category.
If no products match, the system shows an empty-result message without clearing filters.
"""


def _build_two_persona_state() -> tuple[dict, WorkflowStateAdapter]:
    adapter = WorkflowStateAdapter()
    chunks = [
        RetrievedChunk(
            id="CHUNK-MERCHANT",
            content=(
                "The Merchant can add catalog inventory with a unique SKU and price. "
                "The system rejects a duplicate SKU and reports the existing item."
            ),
            metadata={"section_title": "Merchant Use Cases"},
        ),
        RetrievedChunk(
            id="CHUNK-BUYER",
            content=(
                "The Buyer can search the catalog by product name and category. "
                "If no products match, the system shows an empty-result message without clearing filters."
            ),
            metadata={"section_title": "Buyer Use Cases"},
        ),
    ]
    analysis = RequirementAnalysisOutput(
        actors=["Merchant", "Buyer"],
        functional_requirements=[
            "The Merchant can add catalog inventory with a unique SKU and price.",
            "The Buyer can search the catalog by product name and category.",
        ],
        edge_cases=[
            "The system rejects a duplicate SKU and reports the existing item.",
            "If no products match, the system shows an empty-result message without clearing filters.",
        ],
        actor_requirement_mappings=[
            ActorRequirementMapping(
                actor="Merchant",
                requirement="The Merchant can add catalog inventory with a unique SKU and price.",
                chunk_refs=["CHUNK-MERCHANT"],
            ),
            ActorRequirementMapping(
                actor="Buyer",
                requirement="The Buyer can search the catalog by product name and category.",
                chunk_refs=["CHUNK-BUYER"],
            ),
        ],
    )
    state = adapter.requirement_analysis_to_state(
        analysis,
        retrieved_chunks=chunks,
    )
    epic_output = EpicGenerationOutput(
        epics=[
            Epic(
                epic_id="EPIC-001",
                title="Marketplace Operations",
                features=["Add catalog inventory", "Search product catalog"],
                feature_actors={
                    "Add catalog inventory": "Merchant",
                    "Search product catalog": "Buyer",
                },
                one_line_story="As a marketplace participant, I want marketplace access so that I can transact.",
                dependencies=[],
                priority="High",
            )
        ]
    )
    state.update(adapter.epic_generation_to_state(epic_output))
    state["features"] = asyncio.run(EpicFeatureAdapter().execute(state))
    state["one_line_stories"] = asyncio.run(EpicOneLineStoryAdapter().execute(state))
    state.update(
        adapter.one_line_stories_to_state(
            state["one_line_stories"],
            epics=state["epics"],
            features=state["features"],
            retrieved_chunks=chunks,
            agent1_output=state["agent1_output"],
            traceability={},
        )
    )
    state["workflow_id"] = "WF-TWO-PERSONA"
    return state, adapter


def test_two_persona_brd_preserves_actor_scope_through_story_generation() -> None:
    assert "Merchant Use Cases" in TWO_PERSONA_BRD
    assert "Buyer Use Cases" in TWO_PERSONA_BRD
    state, adapter = _build_two_persona_state()

    one_line_by_feature = {
        story.feature_id: story for story in state["one_line_stories"]
    }
    assert one_line_by_feature["EPIC-001-FEAT-001"].actor == "Merchant"
    assert one_line_by_feature["EPIC-001-FEAT-002"].actor == "Buyer"
    assert one_line_by_feature["EPIC-001-FEAT-001"].chunk_refs == ["CHUNK-MERCHANT"]
    assert one_line_by_feature["EPIC-001-FEAT-002"].chunk_refs == ["CHUNK-BUYER"]

    request = adapter.generation_request_from_state(state)
    stories = UserStoryGenerationAgent()._generate_deterministic_stories(request)

    assert [story.persona for story in stories] == ["Merchant", "Buyer"]
    assert stories[0].user_story.startswith("As a Merchant,")
    assert stories[1].user_story.startswith("As a Buyer,")

    normalized_criteria: list[set[str]] = []
    for story in stories:
        feature_name = next(
            feature.name or feature.id
            for feature in request.features
            if feature.id == story.feature_id
        )
        normalized_criteria.append(
            {
                re.sub(
                    re.escape(feature_name.casefold()),
                    "",
                    criterion.description.casefold(),
                )
                for criterion in story.acceptance_criteria
            }
        )
    assert normalized_criteria[0].isdisjoint(normalized_criteria[1])
    assert "unique sku and price" in " ".join(normalized_criteria[0])
    assert "product name and category" in " ".join(normalized_criteria[1])


def test_validator_flags_wrong_actor_and_repeated_generic_acceptance_templates() -> None:
    state, adapter = _build_two_persona_state()
    request = adapter.generation_request_from_state(state)
    stories = UserStoryGenerationAgent()._generate_deterministic_stories(request)
    stories[1].persona = "Merchant"
    stories[1].user_story = stories[1].user_story.replace("As a Buyer,", "As a Merchant,")
    for story in stories:
        story.acceptance_criteria = [
            AcceptanceCriterion(
                id="AC-001",
                description=(
                    f"Given the {story.persona} can access {story.title}, When the capability is used, "
                    f"Then the system presents the behavior associated with that request."
                ),
                source_refs=list(story.chunk_ids_used),
            )
        ]

    validation_request = adapter.validation_request_from_state(
        {**state, "generation_request": request, "user_stories": stories}
    )
    result = UserStoryValidator().validate(validation_request)

    assert any(issue.category == "Persona Correctness" and issue.story_id == stories[1].id for issue in result.issues)
    assert any(
        issue.category == "Acceptance Criteria"
        and "generic template" in issue.message
        for issue in result.issues
    )
