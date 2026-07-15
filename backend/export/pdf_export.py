"""PDF document export functionality using ReportLab.

Generates comprehensive PDF documents containing:
- Epic and Feature information
- User Stories with full details
- Acceptance Criteria
- Business Rules
- Dependencies
- Priority and Story Points
- Additional metadata (persona, business value, confidence, etc.)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from export.formatter import StoryFormatter
from export.models import ExportRequest, ExportResponse, ExportStatus, StoryExportData
from export.utils import ensure_output_directory, generate_export_filename, get_output_base_dir

logger = logging.getLogger("export.pdf_export")


class PDFExporter:
    """Exports user stories to PDF format with comprehensive details.
    
    Generates professional PDF documents containing:
    - Epic and Feature information
    - User Stories with full details
    - Acceptance Criteria
    - Business Rules
    - Dependencies
    - Priority and Story Points
    - Additional metadata (risks, assumptions, DoD, etc.)
    """

    def __init__(self) -> None:
        self.base_dir = get_output_base_dir()
        self.output_dir = ensure_output_directory(self.base_dir, "pdf")
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self) -> None:
        """Set up custom paragraph styles for professional formatting."""
        # Title style
        self.styles.add(
            ParagraphStyle(
                name="CustomTitle",
                parent=self.styles["Heading1"],
                fontSize=28,
                textColor=colors.HexColor("#1f4788"),
                spaceAfter=12,
                spaceBefore=0,
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
            )
        )
        
        # Subtitle style
        self.styles.add(
            ParagraphStyle(
                name="Subtitle",
                parent=self.styles["Normal"],
                fontSize=16,
                textColor=colors.HexColor("#2e5c8a"),
                spaceAfter=24,
                spaceBefore=6,
                alignment=TA_CENTER,
                fontName="Helvetica",
            )
        )
        
        # Story title style
        self.styles.add(
            ParagraphStyle(
                name="StoryTitle",
                parent=self.styles["Heading2"],
                fontSize=14,
                textColor=colors.HexColor("#2e74b5"),
                spaceAfter=12,
                spaceBefore=12,
                fontName="Helvetica-Bold",
            )
        )
        
        # Section heading style
        self.styles.add(
            ParagraphStyle(
                name="SectionHeading",
                parent=self.styles["Heading3"],
                fontSize=11,
                textColor=colors.HexColor("#4a4a4a"),
                spaceAfter=6,
                spaceBefore=12,
                fontName="Helvetica-Bold",
            )
        )
        
        # Epic/Feature style
        self.styles.add(
            ParagraphStyle(
                name="EpicFeature",
                parent=self.styles["Normal"],
                fontSize=10,
                textColor=colors.HexColor("#666666"),
                spaceAfter=8,
                spaceBefore=4,
                fontName="Helvetica",
            )
        )
        
        # Body text style
        self.styles.add(
            ParagraphStyle(
                name="CustomBody",
                parent=self.styles["BodyText"],
                fontSize=10,
                spaceAfter=6,
                spaceBefore=3,
                leading=14,
            )
        )
        
        # Bullet/List style
        self.styles.add(
            ParagraphStyle(
                name="BulletText",
                parent=self.styles["Normal"],
                fontSize=10,
                spaceAfter=4,
                spaceBefore=2,
                leftIndent=20,
                bulletIndent=10,
            )
        )

    def export(self, request: ExportRequest) -> ExportResponse:
        """Export user stories to a PDF document.

        Parameters
        ----------
        request:
            Export request with stories and options.

        Returns
        -------
        ExportResponse
            Export result with file path or error.
        """
        export_id = f"pdf_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        logger.info("Starting PDF export: %s", export_id)

        try:
            filename = request.output_filename or generate_export_filename(
                request.project_name, "pdf"
            )
            file_path = self.output_dir / filename

            self._create_pdf(request, file_path)

            logger.info("PDF export completed: %s", file_path)
            return ExportResponse(
                export_id=export_id,
                status=ExportStatus.COMPLETED,
                format=request.format,
                file_path=str(file_path),
                story_count=len(request.stories),
                completed_at=datetime.utcnow(),
            )

        except Exception as exc:
            logger.exception("PDF export failed: %s", exc)
            return ExportResponse(
                export_id=export_id,
                status=ExportStatus.FAILED,
                format=request.format,
                error_message=str(exc),
                story_count=len(request.stories),
            )

    def _create_pdf(self, request: ExportRequest, file_path: Path) -> None:
        """Create a PDF document with formatted user stories.

        Parameters
        ----------
        request:
            Export request.
        file_path:
            Output file path.
        """
        doc = SimpleDocTemplate(
            str(file_path),
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )

        story_elements = []

        # Title page
        story_elements.extend(self._build_title_page(request))
        story_elements.append(PageBreak())

        # Add each story
        for idx, story in enumerate(request.stories, start=1):
            if idx > 1:
                story_elements.append(PageBreak())
            story_elements.extend(
                self._build_story_elements(story, idx, request.include_metadata)
            )

        doc.build(story_elements)

    def _build_title_page(self, request: ExportRequest) -> list:
        """Build title page elements.

        Parameters
        ----------
        request:
            Export request.

        Returns
        -------
        list
            List of flowable elements for title page.
        """
        elements = []

        # Project title
        title_text = f"{request.project_name}"
        elements.append(Paragraph(title_text, self.styles["CustomTitle"]))

        # Subtitle
        subtitle_text = "User Stories Export"
        elements.append(Paragraph(subtitle_text, self.styles["Subtitle"]))

        # Spacer
        elements.append(Spacer(1, 0.3 * inch))

        # Timestamp
        timestamp_para = Paragraph(
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            self.styles["Italic"]
        )
        timestamp_para.hAlign = "CENTER"
        elements.append(timestamp_para)

        # Story count
        elements.append(Spacer(1, 0.2 * inch))
        count_para = Paragraph(
            f"<b>Total Stories: {len(request.stories)}</b>",
            self.styles["Normal"]
        )
        count_para.hAlign = "CENTER"
        elements.append(count_para)

        # Spacer
        elements.append(Spacer(1, 0.5 * inch))

        # Table of contents note
        toc_heading = Paragraph("<b>Table of Contents</b>", self.styles["Heading2"])
        elements.append(toc_heading)
        elements.append(Spacer(1, 0.1 * inch))
        toc_note = Paragraph(
            "<i>User stories are organized sequentially in this document.</i>",
            self.styles["Italic"]
        )
        elements.append(toc_note)

        return elements

    def _build_story_elements(
        self, story: StoryExportData, story_number: int, include_metadata: bool
    ) -> list:
        """Build PDF elements for a single user story with comprehensive details.

        Parameters
        ----------
        story:
            User story data.
        story_number:
            Sequential story number.
        include_metadata:
            Whether to include metadata section.

        Returns
        -------
        list
            List of reportlab flowable elements.
        """
        elements = []

        # Story title with number
        title_text = f"{story_number}. {StoryFormatter.format_title(story, include_id=True)}"
        elements.append(Paragraph(title_text, self.styles["StoryTitle"]))
        elements.append(Spacer(1, 0.1 * inch))

        # Epic and Feature (if available)
        if story.epic or story.feature:
            epic_feature_parts = []
            if story.epic:
                epic_feature_parts.append(f"<b>Epic:</b> {story.epic}")
            if story.feature:
                epic_feature_parts.append(f"<b>Feature:</b> {story.feature}")
            epic_feature_text = " | ".join(epic_feature_parts)
            elements.append(Paragraph(epic_feature_text, self.styles["EpicFeature"]))
            elements.append(Spacer(1, 0.05 * inch))

        # Priority and Story Points table
        elements.extend(self._build_priority_points_table(story))
        elements.append(Spacer(1, 0.15 * inch))

        # User Story section
        if story.user_story:
            elements.append(Paragraph("<b>User Story</b>", self.styles["SectionHeading"]))
            elements.append(Paragraph(story.user_story, self.styles["CustomBody"]))
            elements.append(Spacer(1, 0.1 * inch))

        # Description section
        elements.append(Paragraph("<b>Description</b>", self.styles["SectionHeading"]))
        elements.append(Paragraph(story.description, self.styles["CustomBody"]))
        elements.append(Spacer(1, 0.1 * inch))

        # Acceptance Criteria section
        elements.extend(self._build_acceptance_criteria_section(story))

        # Business Rules section
        if story.business_rules:
            elements.extend(self._build_business_rules_section(story.business_rules))

        # Dependencies section
        if story.dependencies:
            elements.extend(self._build_dependencies_section(story.dependencies))

        # Additional sections (risks, assumptions, DoD)
        elements.extend(self._build_additional_sections(story))

        # Metadata section
        if include_metadata:
            elements.extend(self._build_metadata_section(story))

        # Horizontal line separator
        elements.append(Spacer(1, 0.1 * inch))
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))

        return elements

    def _build_priority_points_table(self, story: StoryExportData) -> list:
        """Build priority and story points table.

        Parameters
        ----------
        story:
            User story data.

        Returns
        -------
        list
            List of flowable elements.
        """
        elements = []

        # Build table data
        table_data = [
            ["Story ID", "Priority", "Story Points", "Status"],
            [
                story.story_id,
                story.priority or "Not Set",
                str(story.story_points) if story.story_points else "Not Set",
                "⚠ Has Risks" if "has_risks" in story.labels else "Active"
            ]
        ]

        # Create table
        table = Table(table_data, colWidths=[1.5 * inch, 1.5 * inch, 1.5 * inch, 2 * inch])
        table.setStyle(
            TableStyle(
                [
                    # Header row styling
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a90e2")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    # Data row styling
                    ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
                    ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ALIGN", (0, 1), (-1, -1), "CENTER"),
                    # Grid
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )

        elements.append(table)
        return elements

    def _build_acceptance_criteria_section(self, story: StoryExportData) -> list:
        """Build acceptance criteria section.

        Parameters
        ----------
        story:
            User story data.

        Returns
        -------
        list
            List of flowable elements.
        """
        elements = []

        elements.append(Paragraph("<b>Acceptance Criteria</b>", self.styles["SectionHeading"]))

        if story.acceptance_criteria:
            for idx, criterion in enumerate(story.acceptance_criteria, start=1):
                criterion_text = f"{idx}. {criterion}"
                elements.append(Paragraph(criterion_text, self.styles["BulletText"]))
        else:
            elements.append(Paragraph("<i>No acceptance criteria defined.</i>", self.styles["Italic"]))

        elements.append(Spacer(1, 0.1 * inch))
        return elements

    def _build_business_rules_section(self, business_rules: list[str]) -> list:
        """Build business rules section.

        Parameters
        ----------
        business_rules:
            List of business rules.

        Returns
        -------
        list
            List of flowable elements.
        """
        elements = []

        elements.append(Paragraph("<b>Business Rules</b>", self.styles["SectionHeading"]))

        for rule in business_rules:
            rule_text = f"• {rule}"
            elements.append(Paragraph(rule_text, self.styles["BulletText"]))

        elements.append(Spacer(1, 0.1 * inch))
        return elements

    def _build_dependencies_section(self, dependencies: list[Any]) -> list:
        """Build dependencies section with table.

        Parameters
        ----------
        dependencies:
            List of dependencies (can be dicts, strings, or objects).

        Returns
        -------
        list
            List of flowable elements.
        """
        elements = []

        elements.append(Paragraph("<b>Dependencies</b>", self.styles["SectionHeading"]))

        # Build table data
        table_data = [["Dependency ID", "Type", "Description"]]

        for dep in dependencies:
            if isinstance(dep, dict):
                table_data.append([
                    dep.get("id", "N/A"),
                    dep.get("type", "unknown"),
                    dep.get("description", "")
                ])
            elif isinstance(dep, str):
                table_data.append([dep, "reference", ""])
            else:
                table_data.append([str(dep), "unknown", ""])

        # Create table
        table = Table(table_data, colWidths=[1.5 * inch, 1.5 * inch, 3.5 * inch])
        table.setStyle(
            TableStyle(
                [
                    # Header row styling
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5a9bd5")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 10),
                    ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                    # Data rows styling
                    ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                    ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 1), (-1, -1), 9),
                    ("ALIGN", (0, 1), (1, -1), "CENTER"),
                    ("ALIGN", (2, 1), (2, -1), "LEFT"),
                    # Grid
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )

        elements.append(table)
        elements.append(Spacer(1, 0.1 * inch))
        return elements

    def _build_additional_sections(self, story: StoryExportData) -> list:
        """Build additional sections (risks, assumptions, DoD).

        Parameters
        ----------
        story:
            User story data.

        Returns
        -------
        list
            List of flowable elements.
        """
        elements = []

        # Risks
        risks = story.metadata.get("risks", [])
        if risks:
            elements.append(Paragraph("<b>Risks</b>", self.styles["SectionHeading"]))
            for risk in risks:
                risk_text = f"⚠ {risk}"
                elements.append(Paragraph(risk_text, self.styles["BulletText"]))
            elements.append(Spacer(1, 0.1 * inch))

        # Assumptions
        assumptions = story.metadata.get("assumptions", [])
        if assumptions:
            elements.append(Paragraph("<b>Assumptions</b>", self.styles["SectionHeading"]))
            for assumption in assumptions:
                assumption_text = f"• {assumption}"
                elements.append(Paragraph(assumption_text, self.styles["BulletText"]))
            elements.append(Spacer(1, 0.1 * inch))

        # Definition of Done
        if story.definition_of_done:
            elements.append(Paragraph("<b>Definition of Done</b>", self.styles["SectionHeading"]))
            for item in story.definition_of_done:
                dod_text = f"✓ {item}"
                elements.append(Paragraph(dod_text, self.styles["BulletText"]))
            elements.append(Spacer(1, 0.1 * inch))

        return elements

    def _build_metadata_section(self, story: StoryExportData) -> list:
        """Build comprehensive metadata section.

        Parameters
        ----------
        story:
            User story data.

        Returns
        -------
        list
            List of flowable elements.
        """
        elements = []

        # Build metadata rows
        table_data = [["Field", "Value"]]

        # Basic metadata
        if story.assignee:
            table_data.append(["Assignee", story.assignee])

        if story.created_at:
            table_data.append(["Created At", story.created_at.strftime("%Y-%m-%d %H:%M:%S")])

        if story.labels:
            table_data.append(["Labels", ", ".join(story.labels)])

        # Extended metadata
        if "confidence_score" in story.metadata:
            score = story.metadata["confidence_score"]
            table_data.append(["Confidence Score", f"{score:.2%}"])

        if "business_value" in story.metadata:
            table_data.append(["Business Value", story.metadata["business_value"]])

        if "persona" in story.metadata:
            table_data.append(["Persona", story.metadata["persona"]])

        if "goal" in story.metadata:
            table_data.append(["Goal", story.metadata["goal"]])

        if "chunk_ids_used" in story.metadata:
            chunk_ids = story.metadata["chunk_ids_used"]
            if chunk_ids:
                table_data.append(["Source Chunks", f"{len(chunk_ids)} chunks"])

        if story.traceability:
            trace = story.traceability
            if isinstance(trace, dict) and "requirements" in trace:
                reqs = trace["requirements"]
                if isinstance(reqs, list):
                    table_data.append(["Requirements", ", ".join(str(r) for r in reqs)])

        # Only add section if we have metadata
        if len(table_data) > 1:
            elements.append(Paragraph("<b>Metadata</b>", self.styles["SectionHeading"]))

            # Create table
            table = Table(table_data, colWidths=[2 * inch, 4.5 * inch])
            table.setStyle(
                TableStyle(
                    [
                        # Header row styling
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#7fb3d5")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, 0), 10),
                        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
                        # Data rows styling
                        ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                        ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
                        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                        ("FONTNAME", (1, 1), (1, -1), "Helvetica"),
                        ("FONTSIZE", (0, 1), (-1, -1), 9),
                        ("ALIGN", (0, 1), (0, -1), "LEFT"),
                        ("ALIGN", (1, 1), (1, -1), "LEFT"),
                        # Grid
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )

            elements.append(table)
            elements.append(Spacer(1, 0.1 * inch))

        return elements
