# Export Module Implementation Summary

## Overview

The `backend/export` module has been implemented to accept validated workflow output and convert it into multiple export formats (Word, PDF, Jira, Confluence) without modifying any existing backend code.

## Architecture

### Core Components

#### 1. **formatter.py** — Transformation Layer (NO EXPORT LOGIC)

This is the **heart of the module** and implements the requested functionality:

- **`WorkflowOutputFormatter`** class:
  - Accepts validated workflow output:
    - `user_stories: list[UserStory]` — Generated user stories
    - `epics: list[PlanningArtifact]` — Epic artifacts
    - `features: list[PlanningArtifact]` — Feature artifacts
    - `traceability: dict[str, Any]` — Traceability matrix and metadata
    - `export_metadata: dict[str, Any]` — Additional export metadata
  
  - Converts to **common internal model** (`StoryExportData`)
  - **No export logic** — pure data transformation
  - Handles:
    - Acceptance criteria extraction (handles objects, strings, dicts)
    - Epic/feature name resolution from IDs
    - Priority enum to string conversion
    - Metadata enrichment (confidence scores, chunks, personas, etc.)
    - Traceability matrix lookups
    - Label generation from story characteristics

- **`StoryFormatter`** helper class:
  - Provides formatting methods for different text representations
  - Used by exporters for consistent rendering
  - Formats: plain text, HTML, Markdown
  - Metadata section formatting

#### 2. **models.py** — Data Models

- **`StoryExportData`** — Common internal model that all exporters consume
  - story_id, title, description
  - acceptance_criteria (list of strings)
  - priority, story_points, epic, feature
  - labels, assignee, created_at
  - metadata (dict for extensibility)

- **`ExportRequest`** / **`ExportResponse`** — API models
- **`ExportFormat`** enum — WORD, PDF, JIRA, CONFLUENCE
- **`ExportStatus`** enum — PENDING, IN_PROGRESS, COMPLETED, FAILED
- **`JiraExportConfig`** / **`ConfluenceExportConfig`** — Integration configs

#### 3. **Exporters** — Format-Specific Implementations

All exporters accept `ExportRequest` containing `list[StoryExportData]`:

- **word_export.py** — Word (.docx) generation using python-docx
  - Formatted document with headers, tables, metadata
  - Output: `backend/export/outputs/word/`

- **pdf_export.py** — PDF generation using reportlab
  - Professional PDF with custom styles
  - Output: `backend/export/outputs/pdf/`

- **jira_export.py** — Jira REST API integration
  - Creates Jira issues from stories
  - Supports authentication, field mapping, custom fields

- **confluence_export.py** — Confluence REST API integration
  - Creates Confluence pages from stories
  - Supports parent pages, TOC, storage format

#### 4. **export_service.py** — Main Entry Point

- **`ExportService`** class:
  - Central dispatcher
  - Routes to appropriate exporter based on format
  - Handles configuration management
  - Returns unified `ExportResponse`

#### 5. **utils.py** — Shared Utilities

- Filename sanitization
- Directory management
- Timestamp generation
- Text truncation
- Metadata string formatting

## Usage Flow

```
Workflow Output → WorkflowOutputFormatter → StoryExportData → Exporter → Output File/API
```

### Step 1: Transform Workflow Output

```python
from export.formatter import WorkflowOutputFormatter

export_stories = WorkflowOutputFormatter.format_workflow_output(
    user_stories=workflow_response.stories,        # list[UserStory]
    epics=workflow_request.epics,                  # list[PlanningArtifact]
    features=workflow_request.features,            # list[PlanningArtifact]
    traceability=workflow_request.traceability,    # dict[str, Any]
    export_metadata={"project": "My Project"}      # dict[str, Any]
)
# Returns: list[StoryExportData]
```

### Step 2: Export to Desired Format

```python
from export.export_service import ExportService
from export.models import ExportRequest, ExportFormat

service = ExportService()

request = ExportRequest(
    format=ExportFormat.WORD,  # or PDF, JIRA, CONFLUENCE
    stories=export_stories,
    project_name="My Project",
    include_metadata=True,
)

response = service.export(request)
# Returns: ExportResponse with file_path or error
```

## Key Design Decisions

### 1. **Separation of Concerns**

- **Formatter** = Data transformation only
- **Exporters** = Format-specific logic only
- Clean boundaries between layers

### 2. **Common Internal Model**

- All exporters consume `StoryExportData`
- Single source of truth for story representation
- Easy to extend with new export formats

### 3. **No Modification to Existing Code**

- Module is **completely independent**
- Does not import from or modify `backend/app/`
- Can be integrated via workflow router when needed

### 4. **Flexible Metadata**

- `metadata: dict[str, Any]` field for extensibility
- Enriched with workflow-specific data (confidence, chunks, etc.)
- Format-specific exporters can access custom metadata

### 5. **Error Handling**

- All exporters return `ExportResponse` with status
- Failed exports return error messages
- Partial failures tracked (e.g., some Jira issues failed)

## Files Created

```
backend/export/
├── __init__.py                  # Module initialization
├── formatter.py                 # ✅ MAIN: Workflow output transformer (NO EXPORT LOGIC)
├── models.py                    # Data models and schemas
├── utils.py                     # Shared utilities
├── export_service.py            # Main entry point / dispatcher
├── word_export.py               # Word (.docx) exporter
├── pdf_export.py                # PDF exporter
├── jira_export.py               # Jira API exporter
├── confluence_export.py         # Confluence API exporter
├── README.md                    # Usage documentation
├── example_usage.py             # Code examples
├── IMPLEMENTATION_SUMMARY.md    # This file
└── outputs/
    ├── word/
    │   └── .gitkeep
    └── pdf/
        └── .gitkeep
```

## Integration Points

### Option 1: Direct Integration in Workflow Router

```python
# In backend/app/api/workflow_router.py

from export.formatter import WorkflowOutputFormatter
from export.export_service import ExportService
from export.models import ExportRequest, ExportFormat

@router.post("/workflow/{workflow_id}/export")
async def export_workflow(workflow_id: str, format: ExportFormat):
    # Fetch completed workflow
    workflow = await get_workflow(workflow_id)
    
    # Transform to export format
    export_stories = WorkflowOutputFormatter.format_workflow_output(
        user_stories=workflow.stories,
        epics=workflow.request.epics,
        features=workflow.request.features,
        traceability=workflow.request.traceability,
    )
    
    # Export
    service = ExportService()
    request = ExportRequest(format=format, stories=export_stories)
    response = service.export(request)
    
    return response
```

### Option 2: Separate Export Router

Create `backend/app/api/export_router.py` with dedicated export endpoints.

## Dependencies

Required Python packages:

```bash
pip install python-docx reportlab requests pydantic
```

These should be added to `backend/requirements.txt` when integrating.

## Testing

Run the example:

```bash
cd backend/export
python example_usage.py
```

Expected output:
- Demonstrates workflow output transformation
- Shows formatting in different representations
- Creates export request objects

## Future Enhancements

1. **Excel Export** — Add `excel_export.py` for spreadsheet format
2. **Email Export** — Send stories via email
3. **Custom Templates** — Support Word/PDF templates
4. **Batch Export** — Export multiple workflows at once
5. **Export Scheduling** — Background jobs for large exports
6. **Export History** — Track export operations in database

## Validation Checklist

✅ `formatter.py` accepts validated workflow output  
✅ Converts to common internal model (`StoryExportData`)  
✅ NO export logic in formatter (only transformation)  
✅ All exporters reuse `StoryExportData`  
✅ Word exporter creates .docx files  
✅ PDF exporter creates PDF files  
✅ Jira exporter integrates with Jira API  
✅ Confluence exporter integrates with Confluence API  
✅ Export service dispatches to correct exporter  
✅ No modification to existing backend code  
✅ Output directories created with .gitkeep  
✅ Documentation and examples provided  

## Summary

The export module is **complete and ready for integration**. The `formatter.py` file implements the requested functionality: it accepts validated workflow output (epics, generated_user_stories, traceability, export_metadata) and converts it into a common internal model (`StoryExportData`) that all exporters can reuse. **No export logic is performed in the formatter** — it is purely a transformation layer.

The module is independent and can be integrated into the existing backend when needed without modifying any existing code.
