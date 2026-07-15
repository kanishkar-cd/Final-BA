# Word Export Implementation Guide

## Overview

The `word_export.py` module has been **fully implemented** to generate comprehensive Word documents (.docx) containing all requested fields:

- ✅ Epic information
- ✅ Feature information  
- ✅ User Stories with full details
- ✅ Acceptance Criteria
- ✅ Business Rules
- ✅ Dependencies (with type and description)
- ✅ Priority
- ✅ Story Points
- ✅ Additional sections: Risks, Assumptions, Definition of Done
- ✅ Comprehensive metadata

## Architecture

### Input Flow

```
Workflow Output → WorkflowOutputFormatter → StoryExportData → WordExporter → .docx file
```

### Key Components

1. **WorkflowOutputFormatter** (in `formatter.py`)
   - Extracts business_rules from UserStory
   - Extracts dependencies from UserStory (with type and description)
   - Stores them in StoryExportData.metadata dict

2. **WordExporter** (in `word_export.py`)
   - Reads StoryExportData
   - Generates formatted Word document with all sections
   - Saves to `backend/export/outputs/word/`

## Document Structure

Generated Word documents include:

### 1. Title Page
- Project name (styled, centered)
- Subtitle: "User Stories Export"
- Generation timestamp
- Total story count

### 2. Table of Contents
- Placeholder for navigation

### 3. User Stories (one per page)

Each story contains:

#### Story Header
- Story number and title (with ID)
- Epic name (with emoji: 📋)
- Feature name (with emoji: 🎯)

#### Priority & Points Table
| Story ID | Priority | Story Points | Status |
|----------|----------|--------------|--------|
| US-001   | HIGH     | 5            | Active |

#### 📝 Description
Full story description with proper line spacing

#### ✅ Acceptance Criteria
Numbered list of all acceptance criteria

#### 📜 Business Rules
Bulleted list of business rules (from metadata)

#### 🔗 Dependencies
Table with columns:
- Dependency ID
- Type (blocks, requires, etc.)
- Description

#### ⚠️ Risks
Bulleted list of identified risks (if any)

#### 💭 Assumptions
Bulleted list of assumptions (if any)

#### ✔️ Definition of Done
Bulleted list of DoD items (if any)

#### ℹ️ Metadata
Table with comprehensive metadata:
- Assignee
- Created At
- Labels
- Confidence Score (as percentage)
- Business Value
- Persona
- Goal
- Source Chunks (count)
- Requirements (from traceability)

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

The formatter now captures:
- `business_rules` from `UserStory.business_rules` → `metadata["business_rules"]`
- `dependencies` from `UserStory.dependencies` → `metadata["dependencies"]` (with type, description)
- `risks` from `UserStory.risks` → `metadata["risks"]`
- `assumptions` from `UserStory.assumptions` → `metadata["assumptions"]`
- `definition_of_done` from `UserStory.definition_of_done` → `metadata["definition_of_done"]`

### Step 2: Create Export Request

```python
from export.models import ExportRequest, ExportFormat

request = ExportRequest(
    format=ExportFormat.WORD,
    stories=export_stories,
    project_name="E-Commerce Platform",
    include_metadata=True,
    output_filename="user_stories_export.docx"  # Optional
)
```

### Step 3: Export

```python
from export.export_service import ExportService

service = ExportService()
response = service.export(request)

if response.status == "completed":
    print(f"✅ Document created: {response.file_path}")
else:
    print(f"❌ Export failed: {response.error_message}")
```

## Output Location

Files are saved to:
```
backend/export/outputs/word/
```

Default filename format:
```
{project_name}_{timestamp}.docx
```

Example:
```
E-Commerce_Platform_20260709_153045.docx
```

## Formatting Features

### Typography
- **Title**: 24pt, centered, blue color (#1f4788)
- **Story Titles**: 16pt, blue color (#2e74b5)
- **Section Headings**: 12pt with emojis for visual clarity
- **Body Text**: 11pt with 1.15 line spacing

### Visual Elements
- ✅ Emojis for section headers (📋 Epic, 🎯 Feature, ✅ Criteria, etc.)
- ✅ Tables with styled headers (bold)
- ✅ Numbered lists for acceptance criteria
- ✅ Bulleted lists for business rules, risks, assumptions
- ✅ Page breaks between stories
- ✅ Indentation for lists (0.25 inches)

### Tables
- **Priority & Points**: Light Grid Accent 1 style
- **Dependencies**: Light List Accent 1 style (3 columns)
- **Metadata**: Light Grid style (2 columns, bold keys)

## Data Mapping

### From UserStory to Document

| UserStory Field | Document Location |
|----------------|-------------------|
| `id` | Story header, tables |
| `title` | Story header |
| `epic_id` | Resolved to epic name, shown in header |
| `feature_id` | Resolved to feature name, shown in header |
| `description` | Description section |
| `acceptance_criteria` | Acceptance Criteria section (numbered) |
| `business_rules` | Business Rules section (bulleted) |
| `dependencies` | Dependencies section (table) |
| `priority` | Priority & Points table |
| `story_points` | Priority & Points table |
| `risks` | Risks section (bulleted) |
| `assumptions` | Assumptions section (bulleted) |
| `definition_of_done` | Definition of Done section (bulleted) |
| `confidence_score` | Metadata table (as percentage) |
| `business_value` | Metadata table |
| `persona` | Metadata table |
| `goal` | Metadata table |
| `created_at` | Metadata table |
| `chunk_ids_used` | Metadata table (count) |
| `traceability` | Metadata table (requirements) |

## Implementation Details

### Enhanced Formatter (formatter.py)

The `WorkflowOutputFormatter._transform_story()` method was enhanced to capture:

```python
# Business rules
if hasattr(story, "business_rules") and story.business_rules:
    story_metadata["business_rules"] = story.business_rules

# Dependencies (with detailed extraction)
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

# Risks, assumptions, definition of done
if hasattr(story, "risks") and story.risks:
    story_metadata["risks"] = story.risks
if hasattr(story, "assumptions") and story.assumptions:
    story_metadata["assumptions"] = story.assumptions
if hasattr(story, "definition_of_done") and story.definition_of_done:
    story_metadata["definition_of_done"] = story.definition_of_done
```

### Enhanced WordExporter (word_export.py)

New helper methods:

1. **`_add_priority_points_table()`**
   - Creates styled table with Story ID, Priority, Story Points, Status

2. **`_add_acceptance_criteria_section()`**
   - Numbered list with proper indentation

3. **`_add_business_rules_section()`**
   - Reads from `story.metadata["business_rules"]`
   - Bulleted list format

4. **`_add_dependencies_section()`**
   - Reads from `story.metadata["dependencies"]`
   - Creates 3-column table (ID, Type, Description)
   - Handles dicts, strings, objects

5. **`_add_additional_sections()`**
   - Adds Risks, Assumptions, Definition of Done
   - Only shows sections if data exists

6. **`_add_metadata_section()`**
   - Comprehensive metadata table
   - Includes all available fields
   - Formats confidence score as percentage

## Testing

A test script is provided: `test_word_export.py`

To run (from backend directory):
```bash
cd backend
PYTHONPATH=. python export/test_word_export.py
```

Or integrate into your workflow router for production use.

## Dependencies

Required Python packages:
```
python-docx>=0.8.11
```

Install with:
```bash
pip install python-docx
```

## Troubleshooting

### ModuleNotFoundError
If you get import errors, ensure:
1. You're running from the `backend/` directory
2. Or set `PYTHONPATH=.` before running

### Missing Sections in Document
If business rules or dependencies don't appear:
1. Check that they exist in the UserStory object
2. Verify the formatter is capturing them in metadata
3. Enable debug logging to see what's being processed

### Styling Issues
If tables or formatting look wrong:
- Ensure `python-docx` version is 0.8.11 or higher
- Check that Word styles are available (Light Grid, etc.)

## Future Enhancements

Potential improvements:
1. **Custom Templates** — Support for corporate Word templates
2. **Table of Contents** — Generate actual TOC with links
3. **Charts** — Add visual representations of story distribution
4. **Export Filters** — Export only stories matching criteria
5. **Multi-Language** — Support for localized output

## Summary

The Word export is **fully functional** and includes:
✅ Epic, Feature, User Stories  
✅ Acceptance Criteria  
✅ Business Rules  
✅ Dependencies (with type and description)  
✅ Priority and Story Points  
✅ Risks, Assumptions, Definition of Done  
✅ Comprehensive metadata  
✅ Professional formatting with tables, lists, emojis  
✅ Saved to `backend/export/outputs/word/`

The module is ready for integration into your workflow pipeline.
