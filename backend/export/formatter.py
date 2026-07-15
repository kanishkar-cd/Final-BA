"""Formatter module — transforms workflow output into common export models.

This module accepts the validated workflow output (epics, stories, traceability)
and converts it into a standardized internal model (StoryExportData) that all
exporters (Word, PDF, Jira, Confluence) can reuse.

No export logic is performed here — only data transformation and normalization.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from export.models import StoryExportData

logger = logging.getLogger("export.formatter")


class WorkflowOutputFormatter:
    """Transforms validated workflow output into export-ready models.
    
    This class accepts workflow artifacts (UserStory objects, epics, features,
    traceability data) and converts them into StoryExportData instances that
    all exporters can consume.
    """

    @staticmethod
    def format_workflow_output(
        user_stories: list[Any],
        epics: list[Any] | None = None,
        features: list[Any] | None = None,
        traceability: dict[str, Any] | None = None,
        export_metadata: dict[str, Any] | None = None,
    ) -> list[StoryExportData]:
        """Convert workflow output into export-ready story data.

        Parameters
        ----------
        user_stories:
            List of UserStory objects from the workflow.
        epics:
            List of PlanningArtifact objects representing epics.
        features:
            List of PlanningArtifact objects representing features.
        traceability:
            Traceability matrix and metadata.
        export_metadata:
            Additional export metadata (project name, author, etc.).

        Returns
        -------
        list[StoryExportData]
            List of normalized export-ready story data.
        """
        epics_map = WorkflowOutputFormatter._build_artifact_map(epics or [])
        features_map = WorkflowOutputFormatter._build_artifact_map(features or [])
        metadata = export_metadata or {}

        export_stories = []
        for story in user_stories:
            export_story = WorkflowOutputFormatter._transform_story(
                story, epics_map, features_map, traceability, metadata
            )
            export_stories.append(export_story)

        logger.info("Formatted %d stories for export", len(export_stories))
        return export_stories

    @staticmethod
    def _transform_story(
        story: Any,
        epics_map: dict[str, Any],
        features_map: dict[str, Any],
        traceability: dict[str, Any] | None,
        metadata: dict[str, Any],
    ) -> StoryExportData:
        """Transform a single UserStory into StoryExportData.

        Parameters
        ----------
        story:
            UserStory object from workflow.
        epics_map:
            Mapping of epic_id to epic artifact.
        features_map:
            Mapping of feature_id to feature artifact.
        traceability:
            Traceability metadata.
        metadata:
            Export metadata.

        Returns
        -------
        StoryExportData
            Normalized export story data.
        """
        # Extract acceptance criteria text
        acceptance_criteria = []
        if hasattr(story, "acceptance_criteria"):
            for criterion in story.acceptance_criteria:
                if hasattr(criterion, "criterion"):
                    acceptance_criteria.append(criterion.criterion)
                elif isinstance(criterion, str):
                    acceptance_criteria.append(criterion)
                elif isinstance(criterion, dict):
                    acceptance_criteria.append(criterion.get("criterion", str(criterion)))

        # Resolve epic and feature names
        epic_name = None
        if hasattr(story, "epic_id") and story.epic_id:
            epic = epics_map.get(story.epic_id)
            if epic:
                epic_name = getattr(epic, "name", None) or getattr(epic, "description", None)

        feature_name = None
        if hasattr(story, "feature_id") and story.feature_id:
            feature = features_map.get(story.feature_id)
            if feature:
                feature_name = getattr(feature, "name", None) or getattr(feature, "description", None)

        # Extract priority
        priority_value = None
        if hasattr(story, "priority"):
            priority_enum = story.priority
            if hasattr(priority_enum, "value"):
                priority_value = priority_enum.value
            else:
                priority_value = str(priority_enum)

        # Build metadata dictionary
        story_metadata = {}
        if hasattr(story, "metadata") and isinstance(story.metadata, dict):
            story_metadata.update(story.metadata)

        # Add traceability info to metadata
        if traceability and hasattr(story, "id"):
            story_id = story.id
            if "traceability_matrix" in traceability:
                for row in traceability["traceability_matrix"]:
                    if isinstance(row, dict) and row.get("story_id") == story_id:
                        story_metadata["traceability"] = row
                        break

        # Add confidence score
        if hasattr(story, "confidence_score"):
            story_metadata["confidence_score"] = story.confidence_score

        # Add chunk references
        if hasattr(story, "chunk_ids_used") and story.chunk_ids_used:
            story_metadata["chunk_ids_used"] = story.chunk_ids_used

        # Add business value
        if hasattr(story, "business_value") and story.business_value:
            story_metadata["business_value"] = story.business_value

        # Add persona and goal
        if hasattr(story, "persona") and story.persona:
            story_metadata["persona"] = story.persona
        if hasattr(story, "goal") and story.goal:
            story_metadata["goal"] = story.goal

        # Add epic information for Jira export
        epic_name = None
        if hasattr(story, "epic_id") and story.epic_id:
            epic = epics_map.get(story.epic_id)
            if epic:
                epic_name = getattr(epic, "name", None) or getattr(epic, "description", None)
                epic_desc = getattr(epic, "description", None)
                if epic_name:
                    story_metadata["epic_name"] = epic_name
                if epic_desc:
                    story_metadata["epic_description"] = epic_desc

        # Add original issue key for traceability
        if hasattr(story, "original_issue_key") and story.original_issue_key:
            story_metadata["original_issue_key"] = story.original_issue_key
        # Also check in existing metadata
        if hasattr(story, "metadata") and isinstance(story.metadata, dict):
            if "original_issue_key" in story.metadata:
                story_metadata["original_issue_key"] = story.metadata["original_issue_key"]

        # Add business rules
        if hasattr(story, "business_rules") and story.business_rules:
            story_metadata["business_rules"] = story.business_rules

        # Add dependencies
        if hasattr(story, "dependencies") and story.dependencies:
            deps = []
            for dep in story.dependencies:
                if hasattr(dep, "dependency_id"):
                    deps.append({
                        "id": dep.dependency_id,
                        "type": getattr(dep, "dependency_type", "unknown"),
                        "description": getattr(dep, "description", ""),
                    })
                elif isinstance(dep, dict):
                    deps.append(dep)
                elif isinstance(dep, str):
                    deps.append({"id": dep, "type": "reference", "description": ""})
            story_metadata["dependencies"] = deps

        # Add risks
        if hasattr(story, "risks") and story.risks:
            story_metadata["risks"] = story.risks

        # Add assumptions
        if hasattr(story, "assumptions") and story.assumptions:
            story_metadata["assumptions"] = story.assumptions

        # Add definition of done
        if hasattr(story, "definition_of_done") and story.definition_of_done:
            story_metadata["definition_of_done"] = story.definition_of_done

        # Extract labels from various fields
        labels = []
        if hasattr(story, "business_rules") and story.business_rules:
            labels.append("has_business_rules")
        if hasattr(story, "dependencies") and story.dependencies:
            labels.append("has_dependencies")
        if hasattr(story, "risks") and story.risks:
            labels.append("has_risks")

        return StoryExportData(
            story_id=getattr(story, "id", "UNKNOWN"),
            title=getattr(story, "title", "Untitled Story"),
            description=getattr(story, "description", ""),
            acceptance_criteria=acceptance_criteria,
            priority=priority_value,
            story_points=getattr(story, "story_points", None),
            epic=epic_name,
            feature=feature_name,
            labels=labels,
            assignee=metadata.get("assignee"),
            created_at=getattr(story, "generation_timestamp", None),
            metadata=story_metadata,
        )

    @staticmethod
    def _build_artifact_map(artifacts: list[Any]) -> dict[str, Any]:
        """Build a mapping of artifact ID to artifact object.

        Parameters
        ----------
        artifacts:
            List of PlanningArtifact objects (epics or features).

        Returns
        -------
        dict[str, Any]
            Mapping of artifact ID to artifact.
        """
        artifact_map = {}
        for artifact in artifacts:
            artifact_id = getattr(artifact, "id", None)
            if artifact_id:
                artifact_map[artifact_id] = artifact
        return artifact_map


class StoryFormatter:
    """Helper class for formatting StoryExportData into various text formats.
    
    Used by exporters to render story data in different representations
    (plain text, HTML, Markdown, etc.).
    """

    @staticmethod
    def format_title(story: StoryExportData, include_id: bool = True) -> str:
        """Format a story title.

        Parameters
        ----------
        story:
            Story data.
        include_id:
            Whether to include the story ID in the title.

        Returns
        -------
        str
            Formatted title.
        """
        if include_id:
            return f"[{story.story_id}] {story.title}"
        return story.title

    @staticmethod
    def format_description(story: StoryExportData) -> str:
        """Format a story description.

        Parameters
        ----------
        story:
            Story data.

        Returns
        -------
        str
            Formatted description.
        """
        return story.description.strip()

    @staticmethod
    def format_acceptance_criteria(story: StoryExportData) -> str:
        """Format acceptance criteria as a numbered list.

        Parameters
        ----------
        story:
            Story data.

        Returns
        -------
        str
            Formatted acceptance criteria.
        """
        if not story.acceptance_criteria:
            return "No acceptance criteria defined."

        lines = []
        for idx, criterion in enumerate(story.acceptance_criteria, start=1):
            lines.append(f"{idx}. {criterion.strip()}")
        return "\n".join(lines)

    @staticmethod
    def format_metadata_section(story: StoryExportData) -> dict[str, str]:
        """Format story metadata as key-value pairs for display.

        Parameters
        ----------
        story:
            Story data.

        Returns
        -------
        dict
            Metadata key-value pairs.
        """
        metadata: dict[str, str] = {}

        if story.priority:
            metadata["Priority"] = story.priority
        if story.story_points is not None:
            metadata["Story Points"] = str(story.story_points)
        if story.epic:
            metadata["Epic"] = story.epic
        if story.feature:
            metadata["Feature"] = story.feature
        if story.labels:
            metadata["Labels"] = ", ".join(story.labels)
        if story.assignee:
            metadata["Assignee"] = story.assignee
        if story.created_at:
            metadata["Created"] = story.created_at.strftime("%Y-%m-%d %H:%M:%S")

        # Add custom metadata fields
        if story.metadata:
            if "confidence_score" in story.metadata:
                metadata["Confidence Score"] = f"{story.metadata['confidence_score']:.2f}"
            if "business_value" in story.metadata:
                metadata["Business Value"] = story.metadata["business_value"]
            if "persona" in story.metadata:
                metadata["Persona"] = story.metadata["persona"]
            if "goal" in story.metadata:
                metadata["Goal"] = story.metadata["goal"]

        return metadata

    @staticmethod
    def format_plain_text(story: StoryExportData) -> str:
        """Format a story as plain text.

        Parameters
        ----------
        story:
            Story data.

        Returns
        -------
        str
            Plain text representation.
        """
        lines = []
        lines.append(f"Story: {story.story_id}")
        lines.append(f"Title: {story.title}")
        lines.append("")
        lines.append("Description:")
        lines.append(story.description)
        lines.append("")
        lines.append("Acceptance Criteria:")
        if story.acceptance_criteria:
            for idx, criterion in enumerate(story.acceptance_criteria, start=1):
                lines.append(f"  {idx}. {criterion}")
        else:
            lines.append("  (None)")
        lines.append("")

        metadata = StoryFormatter.format_metadata_section(story)
        if metadata:
            lines.append("Metadata:")
            for key, value in metadata.items():
                lines.append(f"  {key}: {value}")

        return "\n".join(lines)

    @staticmethod
    def format_html(story: StoryExportData) -> str:
        """Format a story as HTML.

        Parameters
        ----------
        story:
            Story data.

        Returns
        -------
        str
            HTML representation.
        """
        html_parts = []
        html_parts.append(f"<h2>{StoryFormatter.format_title(story)}</h2>")
        html_parts.append("<p><strong>Description:</strong></p>")
        html_parts.append(f"<p>{story.description}</p>")
        html_parts.append("<p><strong>Acceptance Criteria:</strong></p>")
        if story.acceptance_criteria:
            html_parts.append("<ol>")
            for criterion in story.acceptance_criteria:
                html_parts.append(f"<li>{criterion}</li>")
            html_parts.append("</ol>")
        else:
            html_parts.append("<p><em>No acceptance criteria defined.</em></p>")

        metadata = StoryFormatter.format_metadata_section(story)
        if metadata:
            html_parts.append("<p><strong>Metadata:</strong></p>")
            html_parts.append("<ul>")
            for key, value in metadata.items():
                html_parts.append(f"<li><strong>{key}:</strong> {value}</li>")
            html_parts.append("</ul>")

        return "\n".join(html_parts)

    @staticmethod
    def format_markdown(story: StoryExportData) -> str:
        """Format a story as Markdown.

        Parameters
        ----------
        story:
            Story data.

        Returns
        -------
        str
            Markdown representation.
        """
        lines = []
        lines.append(f"## {StoryFormatter.format_title(story)}")
        lines.append("")
        lines.append("**Description:**")
        lines.append("")
        lines.append(story.description)
        lines.append("")
        lines.append("**Acceptance Criteria:**")
        lines.append("")
        if story.acceptance_criteria:
            for idx, criterion in enumerate(story.acceptance_criteria, start=1):
                lines.append(f"{idx}. {criterion}")
        else:
            lines.append("_(No acceptance criteria defined)_")
        lines.append("")

        metadata = StoryFormatter.format_metadata_section(story)
        if metadata:
            lines.append("**Metadata:**")
            lines.append("")
            for key, value in metadata.items():
                lines.append(f"- **{key}:** {value}")
            lines.append("")

        return "\n".join(lines)
