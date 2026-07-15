"""Metadata persistence — writes JSON files to mcp_server/storage/metadata/.

Metadata is stored only for auditing, traceability, and debugging.
It is **never** returned to the AI pipeline.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("mcp_server.metadata_store")

# Resolve the storage directory relative to this file's location.
_STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage" / "metadata"


def _ensure_storage_dir() -> Path:
    """Create the metadata storage directory if it does not exist."""
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return _STORAGE_DIR


def save_metadata(key: str, data: dict[str, Any]) -> Path:
    """Persist metadata as a JSON file and return the path.

    Parameters
    ----------
    key:
        Used as the filename stem (e.g. ``"PROJ-25"`` → ``PROJ-25.json``).
    data:
        Arbitrary metadata dictionary to serialise.
    """
    storage = _ensure_storage_dir()
    # Sanitise the key so it is safe as a filename
    safe_key = key.replace("/", "_").replace("\\", "_")
    file_path = storage / f"{safe_key}.json"

    try:
        file_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        logger.info("Metadata saved: %s", file_path)
    except Exception:
        logger.exception("Failed to save metadata for key=%s", key)

    return file_path


def load_metadata(key: str) -> dict[str, Any] | None:
    """Load previously stored metadata by key, or return ``None``."""
    safe_key = key.replace("/", "_").replace("\\", "_")
    file_path = _STORAGE_DIR / f"{safe_key}.json"

    if not file_path.exists():
        return None

    try:
        return json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Failed to load metadata for key=%s", key)
        return None
