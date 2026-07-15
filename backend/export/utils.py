"""Utility functions for the export module."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("export.utils")


def sanitize_filename(filename: str) -> str:
    """Sanitize a filename by removing invalid characters.

    Parameters
    ----------
    filename:
        Raw filename string.

    Returns
    -------
    str
        Safe filename with invalid characters replaced by underscores.
    """
    # Remove or replace characters that are invalid in filenames
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(". ")
    # Limit length to 200 characters
    if len(sanitized) > 200:
        sanitized = sanitized[:200]
    return sanitized or "export"


def ensure_output_directory(base_dir: Path, format_dir: str) -> Path:
    """Ensure the output directory exists.

    Parameters
    ----------
    base_dir:
        Base export output directory.
    format_dir:
        Format-specific subdirectory (e.g., "word", "pdf").

    Returns
    -------
    Path
        Resolved output directory path.
    """
    output_dir = base_dir / format_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Output directory ensured: %s", output_dir)
    return output_dir


def generate_export_filename(
    project_name: str,
    format_ext: str,
    timestamp: bool = True,
) -> str:
    """Generate a unique export filename.

    Parameters
    ----------
    project_name:
        Project or export name.
    format_ext:
        File extension (e.g., "docx", "pdf").
    timestamp:
        If True, append a timestamp to ensure uniqueness.

    Returns
    -------
    str
        Generated filename.
    """
    safe_name = sanitize_filename(project_name)
    if timestamp:
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"{safe_name}_{ts}.{format_ext}"
    return f"{safe_name}.{format_ext}"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to a maximum length.

    Parameters
    ----------
    text:
        Text to truncate.
    max_length:
        Maximum character length.
    suffix:
        Suffix to append if truncated.

    Returns
    -------
    str
        Truncated text.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)].rstrip() + suffix


def format_story_id(story_id: str) -> str:
    """Format a story ID for display.

    Parameters
    ----------
    story_id:
        Raw story ID (could be UUID or string).

    Returns
    -------
    str
        Formatted story ID.
    """
    # If it's a UUID, format as US-<first 8 chars>
    if len(story_id) > 20 and "-" in story_id:
        return f"US-{story_id.split('-')[0].upper()}"
    return story_id


def dict_to_metadata_string(data: dict[str, Any]) -> str:
    """Convert a metadata dictionary to a readable string.

    Parameters
    ----------
    data:
        Metadata dictionary.

    Returns
    -------
    str
        Human-readable metadata string.
    """
    lines = []
    for key, value in data.items():
        formatted_key = key.replace("_", " ").title()
        if isinstance(value, (list, tuple)):
            value_str = ", ".join(str(v) for v in value)
        elif isinstance(value, dict):
            value_str = "; ".join(f"{k}: {v}" for k, v in value.items())
        else:
            value_str = str(value)
        lines.append(f"{formatted_key}: {value_str}")
    return "\n".join(lines)


def get_output_base_dir() -> Path:
    """Return the base output directory for exports.

    Returns
    -------
    Path
        Base output directory (backend/export/outputs).
    """
    return Path(__file__).resolve().parent / "outputs"
