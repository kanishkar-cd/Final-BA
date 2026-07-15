from __future__ import annotations

from app.schemas.user_story import (
    MappingReference,
    OneLineStoryInput,
    PlanningArtifact,
    TraceabilityLink,
)


class TraceabilityService:
    def build_story_traceability(
        self,
        *,
        workflow_id: str,
        one_line_story: OneLineStoryInput,
        requirements: list[PlanningArtifact],
        epics: list[PlanningArtifact],
        features: list[PlanningArtifact],
        generated_by: str,
    ) -> TraceabilityLink:
        # A single epic-level one-line story can now cover several features.
        # For a feature-specific evidence pack, the explicitly supplied feature
        # is authoritative; the story's legacy feature_id is only a fallback.
        feature_refs = [item.id for item in features] or [one_line_story.feature_id]
        epic_refs = [one_line_story.epic_id] if one_line_story.epic_id else []
        return TraceabilityLink(
            workflow_id=workflow_id,
            requirement_refs=one_line_story.requirement_refs or [item.id for item in requirements],
            chunk_refs=one_line_story.chunk_refs,
            epic_refs=epic_refs or [item.id for item in epics],
            feature_refs=feature_refs or [item.id for item in features],
            one_line_story_refs=[one_line_story.id],
            dependency_refs=one_line_story.dependency_refs,
            generated_by=generated_by,
        )

    def to_mapping(self, artifacts: list[PlanningArtifact], fallback_id: str | None = None) -> list[MappingReference]:
        if artifacts:
            return [MappingReference(id=item.id, name=item.name, source=item.description) for item in artifacts]
        if fallback_id:
            return [MappingReference(id=fallback_id)]
        return []
