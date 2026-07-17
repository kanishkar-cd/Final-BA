from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import sys
import types
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.epic_agent_2 import Epic, EpicGenerationOutput
from app.agents.requirement_analysis_agent import RequirementAnalysisOutput
from app.orchestrator.langgraph_nodes import WorkflowNodes
from app.orchestrator.langgraph_workflow import LangGraphWorkflow
from app.schemas import Chunk
from app.schemas.user_story import PipelineStatus, RegenerationTarget, ValidationResult


DOCUMENT_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("22222222-2222-2222-2222-222222222222")


class FakeImporter:
    async def import_document(self, file_path: str | Path) -> str:
        return f"parsed:{file_path}"


class FakeChunker:
    def chunk_text(self, text: str, **kwargs: Any) -> list[Chunk]:
        return [
            Chunk.create(
                document_id=UUID(str(kwargs["document_id"])),
                project_id=UUID(str(kwargs["project_id"])),
                chunk_index=0,
                section_title="Authentication",
                content="Users can sign in with OTP.",
                token_count=7,
                metadata={"source": kwargs["source"]},
            )
        ]


class FakeContextLabeler:
    async def label_chunks(self, chunks: list[Chunk]) -> list[Chunk]:
        return [replace(chunk, context="Authentication") for chunk in chunks]


class FakeRequirementAgent:
    async def run(self, chunks: list[dict[str, Any]]) -> RequirementAnalysisOutput:
        return RequirementAnalysisOutput(
            actors=["User"],
            functional_requirements=["Users can sign in with OTP."],
            non_functional_requirements=["OTP must be delivered quickly."],
            dependencies=["OTP Service"],
            business_goals=["Secure access"],
            edge_cases=["OTP expires before completion."],
            constraints=["OTP provider must be available."],
        )


class FakeEpicAgent:
    async def execute(self, payload: dict[str, Any]) -> EpicGenerationOutput:
        return EpicGenerationOutput(
            epics=[
                Epic(
                    epic_id="EPIC-001",
                    title="Authentication",
                    features=["OTP Sign In"],
                    one_line_story=(
                        "As a user, I want to sign in with OTP, so that I can access my account."
                    ),
                    dependencies=["OTP Service"],
                    priority="High",
                )
            ]
        )


class FakeUserStoryAgent:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def execute(self, payload: Any) -> list:
        self.requests.append(payload)
        return []


class FakeValidationAgent:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def execute(self, payload: Any) -> ValidationResult:
        self.requests.append(payload)
        return ValidationResult(
            validation_status=PipelineStatus.VALIDATION_PASSED,
            passed=True,
            confidence_score=1.0,
            threshold=payload.confidence_threshold,
            regeneration_target=RegenerationTarget.NONE,
        )


def test_workflow_nodes_pass_state_through_existing_agents_and_services() -> None:
    user_story_agent = FakeUserStoryAgent()
    validation_agent = FakeValidationAgent()
    nodes = WorkflowNodes(
        importer=FakeImporter(),
        chunker=FakeChunker(),
        context_labeler=FakeContextLabeler(),
        requirement_agent=FakeRequirementAgent(),
        epic_agent=FakeEpicAgent(),
        user_story_agent=user_story_agent,
        validation_agent=validation_agent,
    )

    async def run_nodes() -> dict[str, Any]:
        state: dict[str, Any] = {
            "workflow_id": "WF-LANGGRAPH",
            "file_path": "sample.txt",
            "document_id": DOCUMENT_ID,
            "project_id": PROJECT_ID,
        }
        for node in (
            nodes.preprocessing,
            nodes.requirement_analysis,
            nodes.epic_generation,
            nodes.feature_generation,
            nodes.one_line_story_generation,
            nodes.user_story_generation,
            nodes.validation,
        ):
            state.update(await node(state))
        return state

    state = asyncio.run(run_nodes())

    assert state["parsed_text"] == "parsed:sample.txt"
    assert state["requirement_analysis"]["edge_cases"] == ["OTP expires before completion."]
    assert state["agent1_output"].business_rules == ["OTP provider must be available."]
    assert state["epics"][0].id == "EPIC-001"
    assert state["features"][0].name == "OTP Sign In"
    assert state["one_line_stories"][0].feature_id == state["features"][0].id
    assert user_story_agent.requests[0].workflow_id == "WF-LANGGRAPH"
    assert validation_agent.requests[0].workflow_id == "WF-LANGGRAPH"
    assert state["validation_result"].passed is True


def test_langgraph_workflow_wires_nodes_in_required_sequence(monkeypatch: Any) -> None:
    calls: list[str] = []

    class FakeCompiledGraph:
        def __init__(self, graph: FakeStateGraph) -> None:
            self.graph = graph

        async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
            current = "__start__"
            while current != "__end__":
                next_node = self.graph.edges[current][0]
                if next_node == "__end__":
                    current = next_node
                    continue
                calls.append(next_node)
                state.update(await self.graph.nodes[next_node](state))
                current = next_node
            return state

    class FakeStateGraph:
        def __init__(self, state_type: Any) -> None:
            self.state_type = state_type
            self.nodes: dict[str, Any] = {}
            self.edges: dict[str, list[str]] = {}

        def add_node(self, name: str, node: Any) -> None:
            self.nodes[name] = node

        def add_edge(self, source: str, target: str) -> None:
            self.edges.setdefault(source, []).append(target)

        def compile(self) -> FakeCompiledGraph:
            return FakeCompiledGraph(self)

    fake_module = types.ModuleType("langgraph")
    fake_graph_module = types.ModuleType("langgraph.graph")
    fake_graph_module.START = "__start__"
    fake_graph_module.END = "__end__"
    fake_graph_module.StateGraph = FakeStateGraph
    monkeypatch.setitem(sys.modules, "langgraph", fake_module)
    monkeypatch.setitem(sys.modules, "langgraph.graph", fake_graph_module)

    class FakeNodes:
        async def preprocessing(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def requirement_analysis(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def epic_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def feature_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def one_line_story_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def user_story_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def validation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def guardrails_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def nlp_rag_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def human_review_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

    workflow = LangGraphWorkflow(nodes=FakeNodes(), enable_nlp_rag_hook=False)
    final_state = asyncio.run(workflow.run_workflow({}))

    assert calls == [
        "preprocessing",
        "requirement_analysis",
        "epic_generation",
        "feature_generation",
        "one_line_story_generation",
        "user_story_generation",
        "validation",
    ]
    assert final_state["workflow_status"] == "FAILED"


def test_validation_routing_uses_retry_human_review_and_success_paths() -> None:
    workflow = LangGraphWorkflow(nodes=types.SimpleNamespace(), enable_nlp_rag_hook=False)

    retry_state = {
        "validation_result": ValidationResult(
            validation_status=PipelineStatus.RETRY_REQUIRED,
            passed=False,
            confidence_score=0.4,
            threshold=0.8,
            retry_required=True,
            review_required=False,
            regeneration_target=RegenerationTarget.NONE,
        )
    }
    retry_state.update(
        workflow._validation_transition(retry_state, retry_state["validation_result"])
    )
    assert workflow._route_after_validation(retry_state) == "retry"

    review_state = {
        "validation_result": ValidationResult(
            validation_status=PipelineStatus.REVIEW_REQUIRED,
            passed=False,
            confidence_score=0.4,
            threshold=0.8,
            retry_required=False,
            review_required=True,
            regeneration_target=RegenerationTarget.HUMAN_REVIEW,
        )
    }
    review_state.update(
        workflow._validation_transition(review_state, review_state["validation_result"])
    )
    assert workflow._route_after_validation(review_state) == "human_review"

    success_state = {
        "validation_result": ValidationResult(
            validation_status=PipelineStatus.VALIDATION_PASSED,
            passed=True,
            confidence_score=1.0,
            threshold=0.8,
            retry_required=False,
            review_required=False,
            regeneration_target=RegenerationTarget.NONE,
        )
    }
    success_state.update(
        workflow._validation_transition(success_state, success_state["validation_result"])
    )
    assert workflow._route_after_validation(success_state) == "success"


def test_retry_exhaustion_routes_to_human_review_with_non_completed_status() -> None:
    class RetryExhaustionNodes:
        def __init__(self) -> None:
            self.validation_calls = 0
            self.review_calls = 0

        async def user_story_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def validation(self, state: dict[str, Any]) -> dict[str, Any]:
            self.validation_calls += 1
            return {"validation_result": ValidationResult(
                validation_status=PipelineStatus.VALIDATION_FAILED,
                passed=False,
                confidence_score=0.4,
                threshold=0.8,
                retry_required=True,
                review_required=False,
                regeneration_target=RegenerationTarget.AGENT_3_USER_STORY,
            )}

        async def human_review_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            self.review_calls += 1
            return {"human_review": {"status": "not_configured"}}

    nodes = RetryExhaustionNodes()
    workflow = LangGraphWorkflow(
        nodes=nodes,
        enable_nlp_rag_hook=False,
        enable_human_review_hook=True,
    )
    final_state = asyncio.run(workflow.run_workflow({
        "workflow_id": "WF-RETRY-EXHAUSTED",
        "one_line_stories": [{"id": "OLS-1"}],
        "max_retry_attempts": 2,
    }))

    assert nodes.validation_calls == 3
    assert nodes.review_calls == 1
    assert final_state["retry_count"] == 2
    assert final_state["retry_status"] == "RETRIES_EXHAUSTED"
    assert final_state["review_required"] is True
    assert final_state["review_status"] == "PENDING"
    assert final_state["workflow_status"] == "REVIEW_REQUIRED"
    assert final_state["validation_result"].validation_status == PipelineStatus.VALIDATION_FAILED


def test_validation_pass_after_retry_reports_completed() -> None:
    class PassAfterRetryNodes:
        def __init__(self) -> None:
            self.validation_calls = 0

        async def user_story_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def validation(self, state: dict[str, Any]) -> dict[str, Any]:
            self.validation_calls += 1
            passed = self.validation_calls == 2
            return {"validation_result": ValidationResult(
                validation_status=(
                    PipelineStatus.VALIDATION_PASSED
                    if passed
                    else PipelineStatus.VALIDATION_FAILED
                ),
                passed=passed,
                confidence_score=1.0 if passed else 0.4,
                threshold=0.8,
                retry_required=not passed,
                review_required=False,
                regeneration_target=(
                    RegenerationTarget.NONE
                    if passed
                    else RegenerationTarget.AGENT_3_USER_STORY
                ),
            )}

    nodes = PassAfterRetryNodes()
    workflow = LangGraphWorkflow(nodes=nodes, enable_nlp_rag_hook=False)
    final_state = asyncio.run(workflow.run_workflow({
        "workflow_id": "WF-PASS-AFTER-RETRY",
        "one_line_stories": [{"id": "OLS-1"}],
        "max_retry_attempts": 3,
    }))

    assert nodes.validation_calls == 2
    assert final_state["retry_count"] == 1
    assert final_state["review_required"] is False
    assert final_state["workflow_status"] == "COMPLETED"
    assert final_state["validation_result"].validation_status == PipelineStatus.VALIDATION_PASSED


def test_workflow_tracks_execution_history_and_progress() -> None:
    class TrackingNodes:
        async def preprocessing(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def requirement_analysis(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def epic_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def feature_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def one_line_story_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def user_story_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def validation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {"validation_result": ValidationResult(
                validation_status=PipelineStatus.VALIDATION_PASSED,
                passed=True,
                confidence_score=1.0,
                threshold=0.8,
                retry_required=False,
                review_required=False,
                regeneration_target=RegenerationTarget.NONE,
            )}

        async def guardrails_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def nlp_rag_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def human_review_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

    workflow = LangGraphWorkflow(nodes=TrackingNodes(), enable_nlp_rag_hook=False)
    final_state = asyncio.run(workflow.run_workflow({"workflow_id": "WF-TRACK"}))

    assert final_state["workflow_status"] == "COMPLETED"
    assert final_state["current_node"] == "validation"
    assert final_state["completed_nodes"] == [
        "preprocessing",
        "requirement_analysis",
        "epic_generation",
        "feature_generation",
        "one_line_story_generation",
        "user_story_generation",
        "validation",
    ]
    assert final_state["workflow_progress"] == 100
    assert final_state["execution_history"][0]["node_name"] == "preprocessing"


def test_langgraph_workflow_updates_error_state_before_propagating(monkeypatch: Any) -> None:
    class FakeCompiledGraph:
        def __init__(self, graph: FakeStateGraph) -> None:
            self.graph = graph

        async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
            current = "__start__"
            while current != "__end__":
                next_node = self.graph.edges[current][0]
                if next_node == "__end__":
                    return state
                state.update(await self.graph.nodes[next_node](state))
                current = next_node
            return state

    class FakeStateGraph:
        def __init__(self, state_type: Any) -> None:
            self.nodes: dict[str, Any] = {}
            self.edges: dict[str, list[str]] = {}

        def add_node(self, name: str, node: Any) -> None:
            self.nodes[name] = node

        def add_edge(self, source: str, target: str) -> None:
            self.edges.setdefault(source, []).append(target)

        def compile(self) -> FakeCompiledGraph:
            return FakeCompiledGraph(self)

    fake_module = types.ModuleType("langgraph")
    fake_graph_module = types.ModuleType("langgraph.graph")
    fake_graph_module.START = "__start__"
    fake_graph_module.END = "__end__"
    fake_graph_module.StateGraph = FakeStateGraph
    monkeypatch.setitem(sys.modules, "langgraph", fake_module)
    monkeypatch.setitem(sys.modules, "langgraph.graph", fake_graph_module)

    class FailingNodes:
        async def preprocessing(self, state: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("preprocessing unavailable")

        async def requirement_analysis(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def epic_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def feature_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def one_line_story_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def user_story_generation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def validation(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def guardrails_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def nlp_rag_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

        async def human_review_hook(self, state: dict[str, Any]) -> dict[str, Any]:
            return {}

    state: dict[str, Any] = {}
    workflow = LangGraphWorkflow(nodes=FailingNodes())

    try:
        asyncio.run(workflow.run_workflow(state))
    except RuntimeError as exc:
        assert str(exc) == "preprocessing unavailable"
    else:
        raise AssertionError("Expected RuntimeError")

    assert state["workflow_status"] == "FAILED"
    assert state["failed_node"] == "preprocessing"
    assert state["last_error"]["type"] == "RuntimeError"
    assert state["errors"] == [state["last_error"]]
