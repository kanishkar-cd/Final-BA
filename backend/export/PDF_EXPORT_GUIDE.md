# PDF Export Implementation Guide

## Overview

The `pdf_export.py` module has been **fully implemented** using ReportLab to generate comprehensive PDF documents containing all requested fields:

- ✅ Epic information
- ✅ Feature information  
- ✅ User Stories with full details
- ✅ Acceptance Criteria (numbered)
- ✅ Business Rules (bulleted)
- ✅ Dependencies (3-column table with ID, Type, Description)
- ✅ Priority (styled table)
- ✅ Story Points (styled table)
- ✅ Additional sections: Risks, Assumptions, Definition of Done
- ✅ Comprehensive metadata table

## Architecture

### Input Flow

```
Workflow Output → WorkflowOutputFormatter → StoryExportData → PDFExporter → .pdf file
```

### Key Components

1. **WorkflowOutputFormatter** (in `formatter.py`)
   - Extracts all fields from UserStory
   - Stores business_rules, dependencies, risks, etc. in metadata
   - Returns list[StoryExportData]

2. **PDFExporter** (in `pdf_export.py`)
   - Uses ReportLab for PDF generation
   - Professional styling with custom colors
   - Tables, lists, and proper formatting
   - Saves to `backend/export/outputs/pdf/`

## Document Structure

Generated PDF documents include:

### 1. Title Page
- Project name (28pt, centered, blue #1f4788)
- Subtitle: "User Stories Export" (16pt, blue #2e5c8a)
- Generation timestamp
- Total story count
- Table of contents note

### 2. User Stories (one per page)

Each story contains:

#### Story Header
- Story number and title with ID (14pt, blue #2e74b5)
- Epic: Epic Name | Feature: Feature Name (10pt, grey)

#### Priority & Points Table
Styled table with colored header (#4a90e2):
| Story ID | Priority | Story Points | Status |
|----------|----------|--------------|--------|
| US-001   | HIGH     | 5            | Active |

Background: Beige for data rows

#### Description
- Section heading in bold
- Body text with 14pt leading for readability

#### Acceptance Criteria
- Section heading in bold
- Numbered list (1, 2, 3...) with left indent

#### Business Rules
- Section heading in bold
- Bulleted list (•) with left indent

#### Dependencies Table
3-column styled table with colored header (#5a9bd5):
| Dependency ID | Type    | Description         |
|--------------|---------|---------------------|
| US-002       | blocks  | Depends on US-002   |

#### Risks (if present)
- Bulleted list with ⚠ symbol

#### Assumptions (if present)
- Bulleted list with • symbol

#### Definition of Done (if present)
- Bulleted list with ✓ symbol

#### Metadata Table
2-column styled table with colored header (#7fb3d5):
- Assignee, Created At, Labels
- Confidence Score (as percentage)
- Business Value, Persona, Goal
- Source Chunks (count)
- Requirements (from traceability)

#### Separator
- Horizontal line (grey) between stories

## Visual Features

### Color Scheme
- **Title**: #1f4788 (dark blue)
- **Subtitle**: #2e5c8a (medium blue)
- **Story Titles**: #2e74b5 (bright blue)
- **Section Headings**: #4a4a4a (dark grey)
- **Table Headers**: Various blues (#4a90e2, #5a9bd5, #7fb3d5)
- **Table Data**: White/Beige backgrounds

### Typography
- **Title**: 28pt Helvetica-Bold
- **Subtitle**: 16pt Helvetica
- **Story Titles**: 14pt Helvetica-Bold
- **Section Headings**: 11pt Helvetica-Bold
- **Body Text**: 10pt Helvetica with 14pt leading
- **Tables**: 9-10pt Helvetica

### Layout
- **Margins**: 0.75 inches all around
- **Page Size**: Letter (8.5" × 11")
- **Spacing**: Appropriate spacers between sections
- **Alignment**: 
  - Title/Subtitle: Center
  - Story content: Left
  - Tables: Centered cells for headers/IDs, left for descriptions

## Usage Example

### Step 1: Transform Workflow Output

```python
from export.formatter import WorkflowOutputFormatter

# After workflow completes, transform the output
export_stories = WorkflowOutputFormatter.format_workflow_output(
    user_stories=workflow.stories,           # list[UserStory] from Agent-3
    epics=workflow.request.epics,            # list[PlanningArtifact]
    features=workflow.request.features,      # list[PlanningArtifact]
    traceability=workflow.request.traceability,  # dict with matrix
    export_metadata={"assignee": "john@example.com"}
)
```

### Step 2: Create Export Request

```python
from export.models import ExportRequest, ExportFormat

request = ExportRequest(
    format=ExportFormat.PDF,
    stories=export_stories,
    project_name="E-Commerce Platform",
    include_metadata=True,
    output_filename="user_stories_export.pdf"  # Optional
)
```

### Step 3: Export

```python
from export.export_service import ExportService

service = ExportService()
response = service.export(request)

if response.status == "completed":
    print(f"✅ PDF created: {response.file_path}")
else:
    print(f"❌ Export failed: {response.error_message}")
```

## Output Location

Files are saved to:
```
backend/export/outputs/pdf/
```

Default filename format:
```
{project_name}_{timestamp}.pdf
```

Example:
```
E-Commerce_Platform_20260709_154530.pdf
```

## ReportLab Implementation Details

### Custom Styles

```python
# Title style - 28pt, center, dark blue
CustomTitle (fontSize=28, textColor=#1f4788, alignment=CENTER)

# Subtitle style - 16pt, center, medium blue
Subtitle (fontSize=16, textColor=#2e5c8a, alignment=CENTER)

# Story title style - 14pt, left, bright blue
StoryTitle (fontSize=14, textColor=#2e74b5)

# Section heading style - 11pt, bold, dark grey
SectionHeading (fontSize=11, textColor=#4a4a4a, bold)

# Body text style - 10pt with 14pt leading
CustomBody (fontSize=10, leading=14)

# Bullet text style - 10pt with left indent
BulletText (fontSize=10, leftIndent=20, bulletIndent=10)
```

### Table Styling

#### Priority & Points Table
```python
TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#4a90e2")),  # Blue header
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),        # Beige data
    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
])
```

#### Dependencies Table
```python
TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#5a9bd5")),  # Blue header
    ("ALIGN", (0, 1), (1, -1), "CENTER"),                  # Center ID/Type
    ("ALIGN", (2, 1), (2, -1), "LEFT"),                    # Left Description
])
```

#### Metadata Table
```python
TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), HexColor("#7fb3d5")),  # Light blue header
    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),       # Bold keys
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
])
```

### Flowable Elements

The PDF is built using ReportLab's Platypus framework:

- **Paragraph** — Text with styles
- **Table** — Structured data with styling
- **Spacer** — Vertical spacing (e.g., `Spacer(1, 0.15 * inch)`)
- **PageBreak** — Force new page
- **HRFlowable** — Horizontal line separator

## Data Mapping

### From UserStory to PDF

| UserStory Field | PDF Location | Format |
|----------------|--------------|--------|
| `id` | Story header, tables | Text |
| `title` | Story header | 14pt bold blue |
| `epic_id` | Resolved to epic name | 10pt grey text |
| `feature_id` | Resolved to feature name | 10pt grey text |
| `description` | Description section | Body text |
| `acceptance_criteria` | Numbered list | Indented |
| `business_rules` | Bulleted list | Indented |
| `dependencies` | 3-column table | ID, Type, Desc |
| `priority` | Priority table | Centered |
| `story_points` | Priority table | Centered |
| `risks` | Bulleted list with ⚠ | Indented |
| `assumptions` | Bulleted list with • | Indented |
| `definition_of_done` | Bulleted list with ✓ | Indented |
| `confidence_score` | Metadata table | Percentage |
| `business_value` | Metadata table | Text |
| `persona` | Metadata table | Text |
| `goal` | Metadata table | Text |
| `created_at` | Metadata table | Formatted date |
| `chunk_ids_used` | Metadata table | Count |
| `traceability` | Metadata table | Requirements |

## Testing

A test script is provided: `test_pdf_export.py`

To run (from backend directory):
```bash
cd backend
PYTHONPATH=. python export/test_pdf_export.py
```

Expected output:
- Sample workflow data created
- Transformed using formatter
- Exported to PDF
- Saved to `backend/export/outputs/pdf/test_user_stories.pdf`

## Comparison: PDF vs Word

Both exporters generate similar content with different formats:

| Feature | PDF Export | Word Export |
|---------|-----------|-------------|
| **Epic/Feature** | ✅ Text with colors | ✅ Text with emojis |
| **Priority Table** | ✅ Colored headers | ✅ Styled table |
| **Acceptance Criteria** | ✅ Numbered | ✅ Numbered |
| **Business Rules** | ✅ Bulleted | ✅ Bulleted with emoji |
| **Dependencies** | ✅ 3-column table | ✅ 3-column table |
| **Risks/Assumptions** | ✅ Bulleted with symbols | ✅ Bulleted with emojis |
| **Metadata** | ✅ 2-column table | ✅ 2-column table |
| **Colors** | ✅ Blue headers | ✅ Blue headers |
| **Page Breaks** | ✅ Between stories | ✅ Between stories |
| **Editable** | ❌ Read-only | ✅ Fully editable |

## Dependencies

Required Python packages:
```
reportlab>=3.6.0
```

Install with:
```bash
pip install reportlab
```

## Troubleshooting

### ModuleNotFoundError
If you get import errors:
1. Run from `backend/` directory
2. Or set `PYTHONPATH=.` before running

### Missing Sections in PDF
If business rules or dependencies don't appear:
1. Check that they exist in the UserStory object
2. Verify the formatter is capturing them in metadata
3. Enable debug logging

### Styling Issues
If tables or colors look wrong:
- Ensure `reportlab` version is 3.6.0 or higher
- Check that color codes are valid hex values

### Large Files
For PDFs with many stories:
- Generation may take a few seconds
- File size increases with story count
- Consider splitting into multiple exports if > 100 stories

## Future Enhancements

Potential improvements:
1. **Custom Fonts** — Support for TTF fonts
2. **Images** — Embed diagrams or logos
3. **Charts** — Visual representations of data
4. **Headers/Footers** — Page numbers, project info
5. **Bookmarks** — PDF navigation bookmarks
6. **Hyperlinks** — Clickable links to requirements/dependencies

## Summary

The PDF export is **fully functional** and includes:
✅ Epic, Feature, User Stories  
✅ Acceptance Criteria (numbered)  
✅ Business Rules (bulleted)  
✅ Dependencies (3-column table with ID, Type, Description)  
✅ Priority and Story Points (styled table)  
✅ Risks, Assumptions, Definition of Done  
✅ Comprehensive metadata table  
✅ Professional formatting with colors and styling  
✅ Saved to `backend/export/outputs/pdf/`  
✅ Uses ReportLab for PDF generation  

The module is ready for integration into your workflow pipeline.
