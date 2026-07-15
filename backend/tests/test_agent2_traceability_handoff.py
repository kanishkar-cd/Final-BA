from __future__ import annotations

import pytest

from app.agents.shared_intelligence import (
    EvidencePackBuilder,
    SharedValidators,
    matrix_rows_for_story,
)
from app.orchestrator.langgraph_adapters import WorkflowStateAdapter
from app.schemas.user_story import (
    AcceptanceCriterion,
    Agent1Output,
    Agent2Output,
    GenerateUserStoriesRequest,
    OneLineStoryInput,
    PlanningArtifact,
    RetrievedChunk,
    TraceabilityLink,
    UserStory,
)


def test_agent3_uses_agent2_traceability_for_each_evidence_pack() -> None:
    agent1_output = Agent1Output(
        chunks=[
            RetrievedChunk(id="CHUNK-1", content="Customers can sign in with an OTP."),
            RetrievedChunk(id="CHUNK-2", content="Customers can reset a forgotten password."),
        ],
        functional_requirements=[
            PlanningArtifact(id="REQ-1", name="OTP sign in"),
            PlanningArtifact(id="REQ-2", name="Password reset"),
        ],
    )
    agent2_output = Agent2Output(
        epics=[PlanningArtifact(id="EPIC-1", name="Authentication")],
        features=[
            PlanningArtifact(id="FEATURE-1", name="OTP sign in", metadata={"epic_id": "EPIC-1"}),
            PlanningArtifact(id="FEATURE-2", name="Password reset", metadata={"epic_id": "EPIC-1"}),
        ],
        one_line_stories=[
            OneLineStoryInput(
                id="OLS-1",
                feature_id="FEATURE-1",
                epic_id="EPIC-1",
                summary="As a customer, I want to sign in with an OTP.",
            ),
            OneLineStoryInput(
                id="OLS-2",
                feature_id="FEATURE-2",
                epic_id="EPIC-1",
                summary="As a customer, I want to reset a forgotten password.",
            ),
        ],
        traceability_matrix=[
            {
                "feature_id": "FEATURE-1",
                "one_line_story_id": "OLS-1",
                "chunk_ids": ["CHUNK-1"],
                "requirement_ids": ["REQ-1"],
            },
            {
                "feature_id": "FEATURE-2",
                "one_line_story_id": "OLS-2",
                "chunk_ids": ["CHUNK-2"],
                "requirement_ids": ["REQ-2"],
            },
        ],
        planning_metadata={"source": "agent-2"},
    )
    request = GenerateUserStoriesRequest(
        workflow_id="WF-TRACEABILITY",
        agent1_output=agent1_output,
        agent2_output=agent2_output,
        traceability={"traceability_matrix": [], "planning_metadata": {}},
    )

    evidence_packs = EvidencePackBuilder(request).build()

    assert request.traceability["traceability_matrix"] == agent2_output.traceability_matrix
    assert request.traceability["planning_metadata"] == {"source": "agent-2"}
    assert [pack.chunk_refs for pack in evidence_packs] == [["CHUNK-1"], ["CHUNK-2"]]
    assert [pack.requirement_refs for pack in evidence_packs] == [["REQ-1"], ["REQ-2"]]
    assert [pack.feature.id for pack in evidence_packs] == ["FEATURE-1", "FEATURE-2"]
    assert [pack.one_line_story.id for pack in evidence_packs] == ["OLS-1", "OLS-2"]
    assert [chunk.id for chunk in evidence_packs[0].retrieved_chunks] == ["CHUNK-1"]
    assert [chunk.id for chunk in evidence_packs[1].retrieved_chunks] == ["CHUNK-2"]
    assert evidence_packs[0].traceability_rows == [agent2_output.traceability_matrix[0]]
    assert evidence_packs[1].traceability_rows == [agent2_output.traceability_matrix[1]]

    first_pack = evidence_packs[0]
    story = UserStory(
        id="US-001",
        epic_id="EPIC-1",
        feature_id="FEATURE-1",
        one_line_story_id="OLS-1",
        chunk_ids_used=["CHUNK-1"],
        title="OTP sign in",
        user_story="As a customer, I want to sign in with an OTP.",
        description="Sign in using the mapped OTP evidence.",
        acceptance_criteria=[AcceptanceCriterion(id="AC-001", description="OTP sign in works")],
        traceability=TraceabilityLink(
            workflow_id="WF-TRACEABILITY",
            chunk_refs=["CHUNK-1"],
            epic_refs=["EPIC-1"],
            feature_refs=["FEATURE-1"],
            one_line_story_refs=["OLS-1"],
        ),
    )

    with pytest.raises(ValueError, match="requirement references"):
        SharedValidators.validate_story_against_pack(story, first_pack)

    story.traceability.requirement_refs = ["REQ-1"]
    SharedValidators.validate_story_against_pack(story, first_pack)


def test_shared_planning_story_expands_to_every_feature_without_global_dependencies() -> None:
    chunks = [
        RetrievedChunk(id="CHUNK-1", content="Visitors can view services and contact sales."),
    ]
    agent1 = Agent1Output(
        chunks=chunks,
        functional_requirements=[
            PlanningArtifact(id="REQ-1", name="View services"),
            PlanningArtifact(id="REQ-2", name="Contact sales"),
        ],
        dependencies=["Global project dependency"],
    )
    epic = PlanningArtifact(id="EPIC-1", name="Customer engagement")
    features = [
        PlanningArtifact(
            id="FEATURE-1",
            name="View services",
            metadata={"epic_id": "EPIC-1", "dependencies": ["Service catalogue"]},
        ),
        PlanningArtifact(
            id="FEATURE-2",
            name="Contact sales",
            metadata={"epic_id": "EPIC-1", "dependencies": ["Contact channel"]},
        ),
    ]
    planning_story = OneLineStoryInput(
        id="OLS-1",
        feature_id="FEATURE-1",
        feature_refs=["FEATURE-1", "FEATURE-2"],
        epic_id="EPIC-1",
        summary="As a visitor, I want customer engagement capabilities.",
        chunk_refs=["CHUNK-1"],
        requirement_refs=["REQ-1", "REQ-2"],
    )
    request = GenerateUserStoriesRequest(
        workflow_id="WF-MULTI-FEATURE",
        agent1_output=agent1,
        agent2_output=Agent2Output(
            epics=[epic],
            features=features,
            one_line_stories=[planning_story],
        ),
    )

    packs = EvidencePackBuilder(request).build()

    assert [pack.feature.id for pack in packs] == ["FEATURE-1", "FEATURE-2"]
    assert [pack.dependencies for pack in packs] == [["Service catalogue"], ["Contact channel"]]


def test_traceability_matrix_expands_shared_story_feature_references() -> None:
    planning_story = OneLineStoryInput(
        id="OLS-1",
        feature_id="FEATURE-1",
        feature_refs=["FEATURE-1", "FEATURE-2"],
        epic_id="EPIC-1",
        summary="Engage customers",
        chunk_refs=["CHUNK-1"],
        requirement_refs=["REQ-1"],
    )

    matrix = WorkflowStateAdapter.build_traceability_matrix(
        one_line_stories=[planning_story],
        retrieved_chunks=[],
        requirements=[],
    )

    assert [(row["feature_id"], row["one_line_story_id"]) for row in matrix] == [
        ("FEATURE-1", "OLS-1"),
        ("FEATURE-2", "OLS-1"),
    ]
    expanded_story = UserStory(
        id="US-002",
        feature_id="FEATURE-2",
        epic_id="EPIC-1",
        one_line_story_id="OLS-1",
        title="Engage customers",
        user_story="As a visitor, I want to engage, so that I can get help.",
        description="Customer engagement behavior.",
        traceability=TraceabilityLink(
            workflow_id="WF-1",
            feature_refs=["FEATURE-2"],
            one_line_story_refs=["OLS-1"],
        ),
    )
    assert matrix_rows_for_story(expanded_story, matrix) == [matrix[1]]
