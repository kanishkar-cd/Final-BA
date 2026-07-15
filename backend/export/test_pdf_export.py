"""Test script for PDF export functionality.

This script demonstrates the complete workflow:
1. Create mock workflow output
2. Transform using WorkflowOutputFormatter
3. Export to PDF document
"""

from datetime import datetime

from export.export_service import ExportService
from export.formatter import WorkflowOutputFormatter
from export.models import ExportFormat, ExportRequest


# Reuse mock classes from word export test
class MockAcceptanceCriterion:
    def __init__(self, criterion: str):
        self.criterion = criterion


class MockDependency:
    def __init__(self, dependency_id: str, dependency_type: str = "blocks", description: str = ""):
        self.dependency_id = dependency_id
        self.dependency_type = dependency_type
        self.description = description


class MockUserStory:
    def __init__(
        self,
        id: str,
        title: str,
        description: str,
        acceptance_criteria: list[str],
        business_rules: list[str] = None,
        dependencies: list[str] = None,
        priority: str = "MEDIUM",
        story_points: int = 3,
        epic_id: str | None = None,
        feature_id: str | None = None,
    ):
        self.id = id
        self.title = title
        self.description = description
        self.acceptance_criteria = [MockAcceptanceCriterion(c) for c in acceptance_criteria]
        self.business_rules = business_rules or []
        self.dependencies = [
            MockDependency(dep, "blocks", f"Depends on {dep}") for dep in (dependencies or [])
        ]
        self.priority = priority
        self.story_points = story_points
        self.epic_id = epic_id
        self.feature_id = feature_id
        self.confidence_score = 0.92
        self.chunk_ids_used = ["chunk-1", "chunk-2", "chunk-3"]
        self.business_value = "Improves user experience and reduces support tickets"
        self.persona = "End User"
        self.goal = "Complete tasks efficiently with minimal friction"
        self.generation_timestamp = datetime.utcnow()
        self.metadata = {"source": "AI Generated", "agent": "Agent-3"}
        self.risks = ["API availability", "Network latency"]
        self.assumptions = ["Users have stable internet", "Browser supports HTML5"]
        self.definition_of_done = [
            "Code reviewed",
            "Unit tests passed",
            "Integration tests passed",
            "Deployed to staging",
        ]


class MockPlanningArtifact:
    def __init__(self, id: str, name: str, description: str):
        self.id = id
        self.name = name
        self.description = description


def create_sample_workflow_output():
    """Create sample workflow output for testing."""
    
    # Create user stories
    user_stories = [
        MockUserStory(
            id="US-001",
            title="User Login with Email and Password",
            description=(
                "As a registered user, I want to log in to the system using my email "
                "and password so that I can access my personalized dashboard and account features."
            ),
            acceptance_criteria=[
                "User can enter email address in the login form",
                "User can enter password (masked input)",
                "System validates email format before submission",
                "System authenticates credentials against database",
                "On successful login, user is redirected to dashboard",
                "On failed login, appropriate error message is displayed",
                "Login attempt is logged for security audit",
            ],
            business_rules=[
                "Email must be in valid format (RFC 5322)",
                "Password must be at least 8 characters",
                "Account locks after 5 failed attempts",
                "Session expires after 30 minutes of inactivity",
            ],
            dependencies=["US-002"],
            priority="HIGH",
            story_points=5,
            epic_id="EPIC-001",
            feature_id="FEAT-001",
        ),
        MockUserStory(
            id="US-002",
            title="Password Reset Flow",
            description=(
                "As a user who forgot their password, I want to reset it using my "
                "registered email so that I can regain access to my account."
            ),
            acceptance_criteria=[
                "User clicks 'Forgot Password' link on login page",
                "System prompts for registered email address",
                "System sends reset link to the email",
                "Reset link is valid for 24 hours",
                "User clicks link and is redirected to password reset page",
                "User enters and confirms new password",
                "System validates password strength",
                "Password is successfully updated in database",
            ],
            business_rules=[
                "Reset link expires after 24 hours",
                "New password must be different from last 3 passwords",
                "Email must be verified before reset",
                "Rate limit: 3 reset requests per hour",
            ],
            dependencies=[],
            priority="HIGH",
            story_points=5,
            epic_id="EPIC-001",
            feature_id="FEAT-001",
        ),
        MockUserStory(
            id="US-003",
            title="User Profile Management",
            description=(
                "As a logged-in user, I want to view and update my profile information "
                "so that my account details are always current."
            ),
            acceptance_criteria=[
                "User can view current profile information",
                "User can edit name, phone number, and address",
                "System validates all input fields",
                "User can upload a profile picture",
                "Changes are saved to database",
                "User receives confirmation message",
            ],
            business_rules=[
                "Email address cannot be changed directly (requires verification)",
                "Profile picture must be under 5MB",
                "Allowed image formats: JPG, PNG, GIF",
                "Phone number must be in valid format",
            ],
            dependencies=["US-001"],
            priority="MEDIUM",
            story_points=3,
            epic_id="EPIC-001",
            feature_id="FEAT-002",
        ),
    ]
    
    # Create epics
    epics = [
        MockPlanningArtifact(
            id="EPIC-001",
            name="User Authentication System",
            description="Comprehensive user authentication and authorization system",
        )
    ]
    
    # Create features
    features = [
        MockPlanningArtifact(
            id="FEAT-001",
            name="Login and Password Management",
            description="Core login functionality with password reset capabilities",
        ),
        MockPlanningArtifact(
            id="FEAT-002",
            name="Profile Management",
            description="User profile viewing and editing capabilities",
        ),
    ]
    
    # Create traceability
    traceability = {
        "traceability_matrix": [
            {
                "story_id": "US-001",
                "requirements": ["REQ-001", "REQ-002"],
                "confidence": 0.95,
            },
            {
                "story_id": "US-002",
                "requirements": ["REQ-003"],
                "confidence": 0.90,
            },
            {
                "story_id": "US-003",
                "requirements": ["REQ-004", "REQ-005"],
                "confidence": 0.88,
            },
        ]
    }
    
    # Export metadata
    export_metadata = {
        "project": "E-Commerce Platform",
        "assignee": "john.doe@example.com",
        "version": "1.0",
    }
    
    return user_stories, epics, features, traceability, export_metadata


def test_pdf_export():
    """Test the complete PDF export workflow."""
    
    print("=" * 70)
    print("Testing PDF Export Functionality")
    print("=" * 70)
    
    # Step 1: Create sample workflow output
    print("\n[Step 1] Creating sample workflow output...")
    user_stories, epics, features, traceability, export_metadata = create_sample_workflow_output()
    print(f"✓ Created {len(user_stories)} user stories")
    print(f"✓ Created {len(epics)} epics")
    print(f"✓ Created {len(features)} features")
    
    # Step 2: Transform using formatter
    print("\n[Step 2] Transforming workflow output...")
    export_stories = WorkflowOutputFormatter.format_workflow_output(
        user_stories=user_stories,
        epics=epics,
        features=features,
        traceability=traceability,
        export_metadata=export_metadata,
    )
    print(f"✓ Transformed {len(export_stories)} stories for export")
    
    # Step 3: Create export request
    print("\n[Step 3] Creating export request...")
    request = ExportRequest(
        format=ExportFormat.PDF,
        stories=export_stories,
        project_name="E-Commerce Platform - Authentication Module",
        include_metadata=True,
        output_filename="test_user_stories.pdf",
    )
    print(f"✓ Export request created")
    print(f"  - Format: {request.format.value}")
    print(f"  - Project: {request.project_name}")
    print(f"  - Stories: {len(request.stories)}")
    print(f"  - Metadata: {request.include_metadata}")
    
    # Step 4: Export to PDF
    print("\n[Step 4] Exporting to PDF document...")
    service = ExportService()
    response = service.export(request)
    
    # Step 5: Display results
    print("\n[Step 5] Export Results:")
    print("=" * 70)
    if response.status == "completed":
        print(f"✅ Export SUCCESSFUL")
        print(f"\n📄 File Details:")
        print(f"   Export ID: {response.export_id}")
        print(f"   File Path: {response.file_path}")
        print(f"   Story Count: {response.story_count}")
        print(f"   Created At: {response.created_at}")
        print(f"   Completed At: {response.completed_at}")
        
        print(f"\n📝 Document Contents:")
        print(f"   ✓ Title page with project name")
        print(f"   ✓ {response.story_count} user stories with:")
        print(f"      - Epic and Feature information")
        print(f"      - Priority and Story Points (styled table)")
        print(f"      - Descriptions")
        print(f"      - Acceptance Criteria (numbered)")
        print(f"      - Business Rules (bulleted)")
        print(f"      - Dependencies (3-column table)")
        print(f"      - Risks, Assumptions, Definition of Done")
        print(f"      - Comprehensive metadata (table)")
        print(f"   ✓ Professional formatting with colors")
        print(f"   ✓ Page breaks between stories")
        
        print(f"\n💡 Next Steps:")
        print(f"   1. Open the file: {response.file_path}")
        print(f"   2. Review the formatting and content")
        print(f"   3. Share with stakeholders")
        
    else:
        print(f"❌ Export FAILED")
        print(f"   Error: {response.error_message}")
    
    print("\n" + "=" * 70)
    print("Test completed!")
    print("=" * 70)


if __name__ == "__main__":
    test_pdf_export()
