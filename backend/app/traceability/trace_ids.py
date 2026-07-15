from __future__ import annotations

import re


def format_chunk_id(document_id: str, chunk_index: int) -> str:
    """
    B5.4: Centralized trace ID format.
    Formats a chunk ID as 'CHK-<document_id>-<index>'.
    """
    return f"CHK-{document_id}-{chunk_index}"


def format_epic_id(epic_index: int) -> str:
    """Formats an epic ID as 'EPC-<index>'."""
    return f"EPC-{epic_index:03d}"


def format_story_id(epic_index: int, story_index: int) -> str:
    """Formats a story ID as 'STY-<epic_index>-<story_index>'."""
    return f"STY-{epic_index:03d}-{story_index:03d}"


def is_valid_chunk_id(trace_id: str) -> bool:
    """Validates if a string matches the standard chunk ID format."""
    return bool(re.match(r"^CHK-[a-zA-Z0-9\-]+-\d+$", trace_id))


def is_valid_trace_id(trace_id: str) -> bool:
    """Validates if a string matches any standard trace ID format."""
    if is_valid_chunk_id(trace_id):
        return True
    if bool(re.match(r"^EPC-\d{3}$", trace_id)):
        return True
    if bool(re.match(r"^STY-\d{3}-\d{3}$", trace_id)):
        return True
    return False
