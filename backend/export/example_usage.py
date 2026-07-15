"""Example usage of the export formatter and exporters.

This file demonstrates how to use the export module with workflow output.
"""

from datetime import datetime
from typing import Any

from export.formatter import StoryFormatter, WorkflowOutputFormatter
from export.models import ExportFormat, ExportRequest, StoryExportData


# Mock workflow objects (these would come from your actual workflow)
class MockAcceptanceCriterion:
    def __init__(self, criterion: str):
        self.criterion = criterion


class MockUserStory:
    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        acceptance_criteria: list[str],
        priority: str = "MEDIUM",
        story_points: int = 3,
        epic_id: str | None = None,
        feature_id: str | None = None,
    ):
        self.id = id
        self.title = title
        self.description = description
        self.acceptance_criteria = [MockAcceptanceCriterion(c) for c in acceptance_criteria]
        self.priority = priority
        self.story_points = story_points
        self.epic_id = epic_id
        self.feature_id = feature_id
        self.confidence_score = 0.95
        self.chunk_ids_used = ["chunk-1", "chunk-2"]
        self.business_value = "Improves user experience"
        self.persona = "End User"
        self.goal = "Complete task efficiently"
        self.generation_timestamp = datetime.utcnow()
        self.metadata = {"source": "AI Generated"}
        self.business_rules = ["Rule 1", "Rule 2"]
        self.dependencies = []
        self.risks = ["Risk 1"]


class MockPlanningArtifact:
    def __init__(self, id: str, name: str, description: str):
        self.id = id
        self.name = name
        self.description = description


def example_workflow_output_transformation():
    """Example: Transform workflow output to export format."""
    
    print("=" * 70)
    print("Example 1: Transforming Workflow Output")
    print("=" * 70)
    
    # Mock workflow output
    user_stories = [
        MockUserStory(
            id="US-001",
            title="User can log in with email and password",
            description="As a user, I want to log in with my email and password so that I can access my account securely.",
            acceptance_criteria=[
                "User enters valid email and password",
                "System validates credentials",
                "User is redirected to dashboard on success",
            ],
            priority="HIGH",
            story_points=5,
            epic_id="EPIC-001",
            feature_id="FEAT-001",
        ),
        MockUserStory(
            id="US-002",
            title="User can reset forgotten password",
            description="As a user, I want to reset my password if I forget it so that I can regain access to my account.",
            acceptance_criteria=[
                "User clicks 'Forgot Password' link",
                "System sends reset email to registered address",
                "User clicks link in email and sets new password",
            ],
            priority="MEDIUM",
            story_points=3,
            epic_id="EPIC-001",
            feature_id="FEAT-001",
        ),
    ]
    
    epics = [
        MockPlanningArtifact(
            id="EPIC-001",
            name="User Authentication",
            description="Secure user authentication system",
        )
    ]
    
    features = [
        MockPlanningArtifact(
            id="FEAT-001",
            name="Login System",
            description="Core login functionality",
        )
    ]
    
    traceability = {
        "traceability_matrix": [
            {"story_id": "US-001", "requirements": ["REQ-001"], "confidence": 0.95},
            {"story_id": "US-002", "requirements": ["REQ-002"], "confidence": 0.90},
        ]
    }
    
    export_metadata = {
        "project": "Authentication Service",
        "assignee": "john.doe@example.com",
    }
    
    # Transform workflow output
    export_stories = WorkflowOutputFormatter.format_workflow_output(
        user_stories=user_stories,
        epics=epics,
        features=features,
        traceability=traceability,
        export_metadata=export_metadata,
    )
    
    print(f"\nTransformed {len(export_stories)} stories for export\n")
    
    # Display first story
    story = export_stories[0]
    print(f"Story ID: {story.story_id}")
    print(f"Title: {story.title}")
    print(f"Epic: {story.epic}")
    print(f"Feature: {story.feature}")
    print(f"Priority: {story.priority}")
    print(f"Story Points: {story.story_points}")
    print(f"Labels: {', '.join(story.labels)}")
    print(f"\nDescription:\n{story.description}")
    print(f"\nAcceptance Criteria:")
    for idx, criterion in enumerate(story.acceptance_criteria, start=1):
        print(f"  {idx}. {criterion}")
    
    return export_stories


def example_story_formatting(story: StoryExportData):
    """Example: Format story in different representations."""
    
    print("\n" + "=" * 70)
    print("Example 2: Formatting Story in Different Representations")
    print("=" * 70)
    
    # Plain text format
    print("\n--- Plain Text Format ---\n")
    print(StoryFormatter.format_plain_text(story))
    
    # Markdown format
    print("\n--- Markdown Format ---\n")
    print(StoryFormatter.format_markdown(story))
    
    # HTML format
    print("\n--- HTML Format ---\n")
    print(StoryFormatter.format_html(story))
    
    # Metadata section
    print("\n--- Metadata Section ---\n")
    metadata = StoryFormatter.format_metadata_section(story)
    for key, value in metadata.items():
        print(f"{key}: {value}")


def example_export_request(stories: list[StoryExportData]):
    """Example: Create export requests for different formats."""
    
    print("\n" + "=" * 70)
    print("Example 3: Creating Export Requests")
    print("=" * 70)
    
    # Word export request
    word_request = ExportRequest(
        format=ExportFormat.WORD,
        stories=stories,
        project_name="Authentication Service",
        include_metadata=True,
        output_filename="user_stories.docx",
    )
    print("\n--- Word Export Request ---")
    print(f"Format: {word_request.format.value}")
    print(f"Project: {word_request.project_name}")
    print(f"Story Count: {len(word_request.stories)}")
    print(f"Include Metadata: {word_request.include_metadata}")
    print(f"Output Filename: {word_request.output_filename}")
    
    # PDF export request
    pdf_request = ExportRequest(
        format=ExportFormat.PDF,
        stories=stories,
        project_name="Authentication Service",
        include_metadata=True,
    )
    print("\n--- PDF Export Request ---")
    print(f"Format: {pdf_request.format.value}")
    print(f"Project: {pdf_request.project_name}")
    print(f"Story Count: {len(pdf_request.stories)}")
    
    # Note: Jira and Confluence exports require additional configuration
    print("\n--- Note ---")
    print("Jira and Confluence exports require JiraExportConfig or ConfluenceExportConfig")
    print("See README.md for full examples")


if __name__ == "__main__":
    # Run examples
    export_stories = example_workflow_output_transformation()
    
    if export_stories:
        example_story_formatting(export_stories[0])
        example_export_request(export_stories)
    
    print("\n" + "=" * 70)
    print("Examples completed successfully!")
    print("=" * 70)
