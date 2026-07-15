from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from app.orchestrator.langgraph_nodes import WorkflowNodes
from app.orchestrator.langgraph_state import WorkflowState
from app.regeneration.retry_service import RetryService
from app.schemas.user_story import PipelineStatus, RegenerationTarget

NodeCallable = Callable[[WorkflowState], Awaitable[WorkflowState]]


class LangGraphWorkflow:
    """Reusable LangGraph orchestration layer for the backend pipeline."""

    def __init__(
        self,
        *,
        nodes: WorkflowNodes | None = None,
        enable_guardrails_hook: bool = False,
        enable_nlp_rag_hook: bool = True,
        enable_human_review_hook: bool = False,
    ) -> None:
        self._nodes = nodes or WorkflowNodes()
        self._enable_guardrails_hook = enable_guardrails_hook
        self._enable_nlp_rag_hook = enable_nlp_rag_hook
        self._enable_human_review_hook = enable_human_review_hook
        self._retry_service = RetryService()
        self._core_node_names = [
            "preprocessing",
            "requirement_analysis",
            "epic_generation",
            "feature_generation",
            "one_line_story_generation",
            "user_story_generation",
            "validation",
        ]
        self._compiled_graph = self._build_graph()

    async def run_workflow(self, initial_state: WorkflowState) -> WorkflowState:
        """Run the compiled graph and return the final workflow state."""

        self._seed_state(initial_state)
        return await self._compiled_graph.ainvoke(initial_state)

    def _build_graph(self) -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "LangGraph is required to run the backend orchestration graph. "
                "Install the 'langgraph' package in the backend environment."
            ) from exc

        graph = StateGraph(WorkflowState)
        self._end_node = END

        self._add_node(graph, "preprocessing", self._get_node("preprocessing"))
        self._add_node(graph, "requirement_analysis", self._get_node("requirement_analysis"))
        self._add_node(graph, "epic_generation", self._get_node("epic_generation"))
        self._add_node(graph, "feature_generation", self._get_node("feature_generation"))
        self._add_node(
            graph,
            "one_line_story_generation",
            self._get_node("one_line_story_generation"),
        )
        self._add_node(graph, "user_story_generation", self._get_node("user_story_generation"))
        self._add_node(graph, "validation", self._get_node("validation"))

        if self._enable_guardrails_hook:
            self._add_node(graph, "guardrails_hook", self._get_node("guardrails_hook"))
        if self._enable_nlp_rag_hook:
            self._add_node(graph, "nlp_rag_hook", self._get_node("nlp_rag_hook"))
        if self._enable_human_review_hook:
            self._add_node(graph, "human_review_hook", self._get_node("human_review_hook"))
        elif hasattr(graph, "add_node"):
            self._add_node(graph, "human_review_hook", self._get_node("human_review_hook"))

        graph.add_conditional_edges(
            START,
            self._route_initial_node,
            {
                "preprocessing": "preprocessing",
                "requirement_analysis": "requirement_analysis",
                "epic_generation": "epic_generation",
                "feature_generation": "feature_generation",
                "one_line_story_generation": "one_line_story_generation",
                "user_story_generation": "user_story_generation",
            },
        )
        self._add_optional_edge(
            graph,
            "preprocessing",
            "requirement_analysis",
            optional_node="guardrails_hook",
            enabled=self._enable_guardrails_hook,
        )
        graph.add_edge("requirement_analysis", "epic_generation")
        graph.add_edge("epic_generation", "feature_generation")
        graph.add_edge("feature_generation", "one_line_story_generation")
        self._add_optional_edge(
            graph,
            "one_line_story_generation",
            "user_story_generation",
            optional_node="nlp_rag_hook",
            enabled=self._enable_nlp_rag_hook,
        )
        graph.add_edge("user_story_generation", "validation")
        self._add_validation_edges(graph)

        return graph.compile()

    @staticmethod
    def _route_initial_node(state: WorkflowState) -> str:
        """Resume at the first stage not already supplied by the caller."""
        if state.get("one_line_stories") or state.get("agent2_output"):
            return "user_story_generation"
        if state.get("features"):
            return "one_line_story_generation"
        if state.get("epics"):
            return "feature_generation"
        if state.get("agent1_output") or state.get("requirements") or state.get("requirement_analysis"):
            return "epic_generation"
        if state.get("requirement_chunks") or state.get("retrieved_chunks"):
            return "requirement_analysis"
        return "preprocessing"

    def _add_node(self, graph: Any, node_name: str, node: NodeCallable) -> None:
        graph.add_node(node_name, self._with_error_handling(node_name, node))

    def _get_node(self, node_name: str) -> NodeCallable:
        node = getattr(self._nodes, node_name, None)
        if node is None:
            async def _noop(state: WorkflowState) -> WorkflowState:
                return {}

            return _noop
        return node

    def _with_error_handling(self, node_name: str, node: NodeCallable) -> NodeCallable:
        async def wrapped(state: WorkflowState) -> WorkflowState:
            from app.shared.llm_client import ai_execution_metadata
            token = ai_execution_metadata.set([])
            started_at = datetime.now(timezone.utc)
            self._mark_node_started(state, node_name, started_at)
            try:
                update = await node(state)
                completed_at = datetime.now(timezone.utc)
                duration_ms = round((completed_at - started_at).total_seconds() * 1000, 3)
                self._mark_node_completed(
                    state,
                    node_name=node_name,
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                )
                merged_update = dict(update or {})
                merged_update.update(
                    {
                        "workflow_status": (
                            "COMPLETED"
                            if node_name == "validation"
                            else state.get("workflow_status", "RUNNING")
                        ),
                        "current_node": node_name,
                        "completed_nodes": self._completed_nodes(state),
                        "workflow_progress": self._workflow_progress(state),
                    }
                )
                node_metadata = ai_execution_metadata.get()
                if node_metadata:
                    if "metadata" not in state or not isinstance(state["metadata"], dict):
                        state["metadata"] = {}
                    state["metadata"].setdefault("ai_execution_metadata", [])
                    state["metadata"]["ai_execution_metadata"].extend(node_metadata)
                    
                    if "metadata" not in merged_update or not isinstance(merged_update["metadata"], dict):
                        merged_update["metadata"] = dict(state.get("metadata", {}))
                    merged_update["metadata"].setdefault("ai_execution_metadata", [])
                    merged_update["metadata"]["ai_execution_metadata"] = list(state["metadata"]["ai_execution_metadata"])

                state.update(merged_update)
                return state
            except Exception as exc:
                node_metadata = ai_execution_metadata.get()
                if node_metadata:
                    if "metadata" not in state or not isinstance(state["metadata"], dict):
                        state["metadata"] = {}
                    state["metadata"].setdefault("ai_execution_metadata", [])
                    state["metadata"]["ai_execution_metadata"].extend(node_metadata)

                completed_at = datetime.now(timezone.utc)
                duration_ms = round((completed_at - started_at).total_seconds() * 1000, 3)
                error = {
                    "node": node_name,
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                }
                state["workflow_status"] = "FAILED"
                state["failed_node"] = node_name
                state["last_error"] = error
                state["errors"] = [*state.get("errors", []), error]
                state.setdefault("failed_nodes", [])
                if node_name not in state["failed_nodes"]:
                    state["failed_nodes"] = [*state["failed_nodes"], node_name]
                self._record_execution_event(
                    state,
                    node_name=node_name,
                    status="FAILED",
                    started_at=started_at,
                    completed_at=completed_at,
                    duration_ms=duration_ms,
                    error=error,
                )
                raise
            finally:
                ai_execution_metadata.reset(token)

        return wrapped

    @staticmethod
    def _add_optional_edge(
        graph: Any,
        source: str,
        target: str,
        *,
        optional_node: str,
        enabled: bool,
    ) -> None:
        if enabled:
            graph.add_edge(source, optional_node)
            graph.add_edge(optional_node, target)
            return
        graph.add_edge(source, target)

    def _add_validation_edges(self, graph: Any) -> None:
        if hasattr(graph, "add_conditional_edges"):
            try:
                graph.add_conditional_edges(
                    "validation",
                    self._route_after_validation,
                    {
                        "success": self._end_node,
                        "retry": "user_story_generation",
                        "human_review": "human_review_hook",
                        "failure": self._end_node,
                    },
                )
            except TypeError:
                graph.add_edge("validation", self._end_node)
            if self._enable_human_review_hook:
                graph.add_edge("human_review_hook", self._end_node)
            return

        if self._enable_human_review_hook:
            graph.add_edge("validation", "human_review_hook")
            graph.add_edge("human_review_hook", self._end_node)
            return
        graph.add_edge("validation", self._end_node)

    def _route_after_validation(self, state: WorkflowState) -> str:
        validation_result = state.get("validation_result")
        if validation_result is None:
            state["workflow_status"] = "FAILED"
            state["failed_node"] = "validation"
            state["last_error"] = {
                "node": "validation",
                "type": "ValueError",
                "message": "validation_result is missing",
            }
            return "failure"

        retry_count = int(state.get("retry_count", 0))
        max_retry_attempts = int(state.get("max_retry_attempts", 3))
        if (
            getattr(validation_result, "retry_required", False)
            and self._retry_service.should_retry(
                validation_result,
                retry_count,
                max_retry_attempts,
            )
        ):
            state["retry_count"] = retry_count + 1
            state["retry_reason"] = "validation_requested_retry"
            state["retry_status"] = "RETRY_REQUIRED"
            state["review_required"] = False
            state["review_status"] = "RETRY_PENDING"
            state["approval_status"] = "NOT_REQUIRED"
            state["workflow_status"] = "RETRY_REQUIRED"
            state["retry_history"] = [
                *state.get("retry_history", []),
                {
                    "retry_count": retry_count + 1,
                    "reason": "validation_requested_retry",
                    "status": "RETRY_REQUIRED",
                },
            ]
            state["warnings"] = [
                *state.get("warnings", []),
                "Validation requested a retry; workflow is looping back to user story generation.",
            ]
            return "retry"

        if (
            getattr(validation_result, "review_required", False)
            or getattr(validation_result, "regeneration_target", None)
            == RegenerationTarget.HUMAN_REVIEW
        ):
            state["review_required"] = True
            state["review_status"] = "PENDING"
            state["approval_status"] = "PENDING"
            state["workflow_status"] = "REVIEW_REQUIRED"
            return "human_review"

        if getattr(validation_result, "passed", False):
            state["review_required"] = False
            state["review_status"] = "NOT_REQUIRED"
            state["approval_status"] = "NOT_REQUIRED"
            state["workflow_status"] = "COMPLETED"
            return "success"

        state["review_required"] = False
        state["review_status"] = "FAILED"
        state["approval_status"] = "REJECTED"
        state["workflow_status"] = "FAILED"
        return "failure"

    def _seed_state(self, state: WorkflowState) -> None:
        state.setdefault("workflow_status", "RUNNING")
        state.setdefault("errors", [])
        state.setdefault("failed_node", None)
        state.setdefault("last_error", None)
        state.setdefault("current_node", "START")
        state.setdefault("completed_nodes", [])
        state.setdefault("failed_nodes", [])
        state.setdefault("retry_count", 0)
        state.setdefault("retry_reason", None)
        state.setdefault("retry_status", None)
        state.setdefault("retry_history", [])
        state.setdefault("review_required", False)
        state.setdefault("review_status", None)
        state.setdefault("approval_status", None)
        state.setdefault("execution_history", [])
        state.setdefault("workflow_progress", 0)
        state.setdefault("warnings", [])
        state.setdefault("node_execution_log", [])
        state.setdefault("audit_log", [])
        state.setdefault("execution_time", None)

    def _mark_node_started(self, state: WorkflowState, node_name: str, started_at: datetime) -> None:
        state["current_node"] = node_name
        state["workflow_status"] = "RUNNING"
        self._record_execution_event(
            state,
            node_name=node_name,
            status="RUNNING",
            started_at=started_at,
            completed_at=started_at,
            duration_ms=0.0,
        )

    def _mark_node_completed(
        self,
        state: WorkflowState,
        *,
        node_name: str,
        started_at: datetime,
        completed_at: datetime,
        duration_ms: float,
    ) -> None:
        if node_name not in state.get("completed_nodes", []):
            state["completed_nodes"] = [*state.get("completed_nodes", []), node_name]
        state["current_node"] = node_name
        state["workflow_progress"] = self._workflow_progress(state)
        self._record_execution_event(
            state,
            node_name=node_name,
            status="COMPLETED",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )

    def _record_execution_event(
        self,
        state: WorkflowState,
        *,
        node_name: str,
        status: str,
        started_at: datetime,
        completed_at: datetime,
        duration_ms: float,
        error: dict[str, Any] | None = None,
    ) -> None:
        execution_event = {
            "node_name": node_name,
            "status": status,
            "started_at": started_at.isoformat(),
            "completed_at": completed_at.isoformat(),
            "duration_ms": duration_ms,
            "error": error,
        }
        state["execution_history"] = [
            *state.get("execution_history", []),
            execution_event,
        ]
        state["node_execution_log"] = state.get("execution_history", [])
        state["audit_log"] = state.get("execution_history", [])
        state["execution_time"] = duration_ms

    def _completed_nodes(self, state: WorkflowState) -> list[str]:
        return list(state.get("completed_nodes", []))

    def _workflow_progress(self, state: WorkflowState) -> int:
        completed = len(state.get("completed_nodes", []))
        total = max(1, len(self._core_node_names))
        return min(100, int((completed / total) * 100))


async def run_workflow(
    initial_state: WorkflowState,
    *,
    nodes: WorkflowNodes | None = None,
    enable_guardrails_hook: bool = False,
    enable_nlp_rag_hook: bool = False,
    enable_human_review_hook: bool = False,
) -> WorkflowState:
    """Convenience entry point for running the backend LangGraph workflow."""

    workflow = LangGraphWorkflow(
        nodes=nodes,
        enable_guardrails_hook=enable_guardrails_hook,
        enable_nlp_rag_hook=enable_nlp_rag_hook,
        enable_human_review_hook=enable_human_review_hook,
    )
    return await workflow.run_workflow(initial_state)
