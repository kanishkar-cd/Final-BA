"""Compatibility entrypoint for uvicorn when launched from the repository root."""

from pathlib import Path
import sys

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
_FRAMEWORK_DIR = Path(__file__).resolve().parent.parent / "framework"

for path in (_BACKEND_DIR, _FRAMEWORK_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from backend.app.main import app  # type: ignore  # noqa: F401,E402

__all__ = ["app"]
