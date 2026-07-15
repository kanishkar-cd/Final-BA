import os
import sys

# Add backend directory to sys.path so we can import modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from export.router import _map_agent4_to_story_export_data
from export.models import ExportRequest, ExportFormat
from export.export_service import ExportService

story_dict = {
    "id": "ST-001",
    "title": "Test Story",
    "user_story": "As a user, I want to test.",
    "description": "This is a test description.",
    "acceptance_criteria": [{"id": "ac1", "description": "AC 1"}, "AC 2"],
    "business_rules": ["Rule 1"],
    "dependencies": [{"id": "DEP-1", "type": "BLOCKS", "description": "A block"}],
    "definition_of_done": ["DoD 1"],
    "priority": "HIGH",
    "story_points": 5,
    "epic_id": "EPIC-1",
    "feature_id": "FEAT-1",
    "traceability": {"requirements": ["REQ-1"]}
}

export_data = _map_agent4_to_story_export_data(story_dict)

print("Mapped Data:")
print(export_data.model_dump_json(indent=2))

request = ExportRequest(
    format=ExportFormat.WORD,
    stories=[export_data],
    project_name="API Test",
    output_filename="api_test.docx"
)

service = ExportService()
result = service.export(request)
print("Word Export Status:", result.status)

request.format = ExportFormat.PDF
request.output_filename = "api_test.pdf"
result2 = service.export(request)
print("PDF Export Status:", result2.status)
