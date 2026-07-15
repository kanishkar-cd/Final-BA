from __future__ import annotations

from app.schemas.user_story import (
    AuditAction,
    AuditEvent,
    PipelineStatus,
    WorkflowHistoryEvent,
)


class WorkflowManager:
    def __init__(self) -> None:
        self._history: dict[str, list[WorkflowHistoryEvent]] = {}
        self._audit: dict[str, list[AuditEvent]] = {}

    def transition(
        self,
        *,
        workflow_id: str,
        from_status: PipelineStatus | None,
        to_status: PipelineStatus,
        message: str,
        metadata: dict | None = None,
    ) -> WorkflowHistoryEvent:
        event = WorkflowHistoryEvent(
            workflow_id=workflow_id,
            from_status=from_status,
            to_status=to_status,
            message=message,
            metadata=metadata or {},
        )
        self._history.setdefault(workflow_id, []).append(event)
        return event

    def audit(
        self,
        *,
        workflow_id: str,
        action: AuditAction,
        actor: str,
        message: str,
        metadata: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            workflow_id=workflow_id,
            action=action,
            actor=actor,
            message=message,
            metadata=metadata or {},
        )
        self._audit.setdefault(workflow_id, []).append(event)
        return event

    def history_for(self, workflow_id: str) -> list[WorkflowHistoryEvent]:
        return list(self._history.get(workflow_id, []))

    def audit_for(self, workflow_id: str) -> list[AuditEvent]:
        return list(self._audit.get(workflow_id, []))
