"""Test script for Jira export functionality.

This script demonstrates the complete Jira export workflow:
1. Create mock workflow output with epic and stories
2. Transform using WorkflowOutputFormatter
3. Export to Jira (creates Epic + Stories)

NOTE: This requires Jira credentials in .env:
- JIRA_BASE_URL
- JIRA_EMAIL
- JIRA_API_TOKEN
"""

from datetime import datetime

from export.export_service import ExportService
from export.formatter import WorkflowOutputFormatter
from export.models import ExportFormat, ExportRequest, JiraExportConfig


# Mock workflow objects
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
        original_issue_key: str | None = None,
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
        self.original_issue_key = original_issue_key
        self.confidence_score = 0.92
        self.chunk_ids_used = ["chunk-1", "chunk-2"]
        self.business_value = "Improves user experience"
        self.persona = "End User"
        self.goal = "Complete tasks efficiently"
        self.generation_timestamp = datetime.utcnow()
        self.metadata = {"source": "AI Generated", "original_issue_key": original_issue_key}
        self.risks = ["API availability"]
        self.assumptions = ["Users have stable internet"]
        self.definition_of_done = [
            "Code reviewed",
            "Unit tests passed",
            "Deployed to staging",
        ]


class MockPlanningArtifact:
    def __init__(self, id: str, name: str, description: str):
        self.id = id
        self.name = name
        self.description = description


def create_sample_workflow_output():
    """Create sample workflow output for Jira export testing."""
    
    # Create user stories
    user_stories = [
        MockUserStory(
            id="US-001",
            title="User Login with Email and Password",
            description=(
                "As a registered user, I want to log in using my email and password "
                "so that I can access my account."
            ),
            acceptance_criteria=[
                "User can enter email address",
                "User can enter password (masked)",
                "System validates credentials",
                "User is redirected to dashboard on success",
            ],
            business_rules=[
                "Email must be valid format",
                "Password must be at least 8 characters",
                "Account locks after 5 failed attempts",
            ],
            dependencies=[],
            priority="HIGH",
            story_points=5,
            epic_id="EPIC-001",
            feature_id="FEAT-001",
            original_issue_key="PROJ-100",  # Original requirement issue
        ),
        MockUserStory(
            id="US-002",
            title="Password Reset Flow",
            description=(
                "As a user who forgot their password, I want to reset it "
                "so that I can regain access to my account."
            ),
            acceptance_criteria=[
                "User clicks 'Forgot Password' link",
                "System sends reset link to email",
                "Reset link is valid for 24 hours",
                "User sets new password",
            ],
            business_rules=[
                "Reset link expires after 24 hours",
                "New password must be different from last 3",
            ],
            dependencies=["US-001"],
            priority="HIGH",
            story_points=5,
            epic_id="EPIC-001",
            feature_id="FEAT-001",
            original_issue_key="PROJ-101",
        ),
        MockUserStory(
            id="US-003",
            title="User Profile Management",
            description=(
                "As a logged-in user, I want to update my profile information "
                "so that my details are current."
            ),
            acceptance_criteria=[
                "User can view current profile",
                "User can edit name, phone, address",
                "System validates input fields",
                "Changes are saved to database",
            ],
            business_rules=[
                "Email cannot be changed directly",
                "Profile picture must be under 5MB",
            ],
            dependencies=["US-001"],
            priority="MEDIUM",
            story_points=3,
            epic_id="EPIC-001",
            feature_id="FEAT-002",
            original_issue_key="PROJ-102",
        ),
    ]
    
    # Create epics
    epics = [
        MockPlanningArtifact(
            id="EPIC-001",
            name="User Authentication System",
            description="Comprehensive authentication and authorization system with login, password management, and profile features",
        )
    ]
    
    # Create features
    features = [
        MockPlanningArtifact(
            id="FEAT-001",
            name="Login and Password Management",
            description="Core login with password reset",
        ),
        MockPlanningArtifact(
            id="FEAT-002",
            name="Profile Management",
            description="User profile editing",
        ),
    ]
    
    # Create traceability
    traceability = {
        "traceability_matrix": [
            {"story_id": "US-001", "requirements": ["REQ-001"], "confidence": 0.95},
            {"story_id": "US-002", "requirements": ["REQ-002"], "confidence": 0.90},
            {"story_id": "US-003", "requirements": ["REQ-003"], "confidence": 0.88},
        ]
    }
    
    # Export metadata
    export_metadata = {
        "project": "E-Commerce Platform",
        "assignee": "john.doe@example.com",
    }
    
    return user_stories, epics, features, traceability, export_metadata


def run_jira_export_demo():
    """Test the complete Jira export workflow."""
    
    print("=" * 70)
    print("Testing Jira Export Functionality")
    print("=" * 70)
    
    # Check for Jira credentials
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    jira_url = os.getenv("JIRA_BASE_URL")
    jira_email = os.getenv("JIRA_EMAIL")
    jira_token = os.getenv("JIRA_API_TOKEN")
    
    if not all([jira_url, jira_email, jira_token]):
        print("\n❌ ERROR: Jira credentials not found in .env")
        print("\nPlease ensure the following are set in backend/.env:")
        print("  - JIRA_BASE_URL=https://your-domain.atlassian.net")
        print("  - JIRA_EMAIL=your-email@example.com")
        print("  - JIRA_API_TOKEN=your-api-token")
        return
    
    print("\n✓ Jira credentials found")
    print(f"  Base URL: {jira_url}")
    print(f"  Email: {jira_email}")
    
    # Get project key from user
    print("\n" + "=" * 70)
    project_key = input("Enter Jira Project Key (e.g., PROJ): ").strip().upper()
    if not project_key:
        print("❌ Project key is required")
        return
    
    print(f"✓ Using project key: {project_key}")
    
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
    
    # Verify epic metadata was captured
    first_story = export_stories[0]
    if "epic_name" in first_story.metadata:
        print(f"✓ Epic metadata captured: {first_story.metadata['epic_name']}")
    
    # Step 3: Create Jira config
    print("\n[Step 3] Creating Jira export config...")
    jira_config = JiraExportConfig(
        project_key=project_key,
        issue_type="Story",
        base_url=jira_url,
        email=jira_email,
        api_token=jira_token,
        assign_to_me=False,
        default_priority="Medium",
    )
    print(f"✓ Jira config created for project {project_key}")
    
    # Step 4: Create export request
    print("\n[Step 4] Creating export request...")
    request = ExportRequest(
        format=ExportFormat.JIRA,
        stories=export_stories,
        project_name="E-Commerce Platform - Authentication",
        include_metadata=True,
    )
    print(f"✓ Export request created")
    print(f"  - Format: {request.format.value}")
    print(f"  - Stories: {len(request.stories)}")
    
    # Step 5: Export to Jira
    print("\n[Step 5] Exporting to Jira...")
    print("  ⏳ Creating Epic and Stories in Jira...")
    print("  (This may take 10-30 seconds)")
    
    service = ExportService()
    response = service.export(request, jira_config=jira_config)
    
    # Step 6: Display results
    print("\n[Step 6] Export Results:")
    print("=" * 70)
    if response.status == "completed":
        print(f"✅ Export SUCCESSFUL")
        print(f"\n📋 Epic Created:")
        print(f"   Epic Key: {response.file_path}")
        print(f"   Epic URL: {response.download_url}")
        print(f"\n📝 Stories Created: {response.story_count}")
        print(f"\n🔗 Hierarchy:")
        print(f"   Epic: {response.file_path}")
        print(f"   └─ {response.story_count} child Stories")
        print(f"\n💡 What was created:")
        print(f"   1. Epic: User Authentication System")
        print(f"   2. Story: User Login with Email and Password")
        print(f"      └─ Linked to Epic as parent")
        print(f"      └─ Traceability link to PROJ-100 (if exists)")
        print(f"   3. Story: Password Reset Flow")
        print(f"      └─ Linked to Epic as parent")
        print(f"      └─ Traceability link to PROJ-101 (if exists)")
        print(f"   4. Story: User Profile Management")
        print(f"      └─ Linked to Epic as parent")
        print(f"      └─ Traceability link to PROJ-102 (if exists)")
        
        print(f"\n📊 Each Story contains:")
        print(f"   ✓ Description")
        print(f"   ✓ Acceptance Criteria")
        print(f"   ✓ Business Rules")
        print(f"   ✓ Dependencies")
        print(f"   ✓ Risks and Assumptions")
        print(f"   ✓ Definition of Done")
        print(f"   ✓ Priority and Story Points")
        
        print(f"\n🔍 Next Steps:")
        print(f"   1. Open Jira: {response.download_url}")
        print(f"   2. Review the Epic and child Stories")
        print(f"   3. Verify traceability links")
        
    else:
        print(f"❌ Export FAILED")
        print(f"   Error: {response.error_message}")
        print(f"\n💡 Troubleshooting:")
        print(f"   - Verify Jira credentials in .env")
        print(f"   - Ensure project key '{project_key}' exists")
        print(f"   - Check that you have permission to create Epics and Stories")
        print(f"   - Verify custom field IDs (Epic Link, Story Points) match your Jira")
    
    print("\n" + "=" * 70)
    print("Test completed!")
    print("=" * 70)


if __name__ == "__main__":
    run_jira_export_demo()
