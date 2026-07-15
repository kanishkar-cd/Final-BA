"""Compatibility package so uvicorn can resolve the backend app from the repo root."""

from pathlib import Path
import sys

_BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
_BACKEND_APP_DIR = _BACKEND_DIR / "app"
_FRAMEWORK_DIR = Path(__file__).resolve().parent.parent / "framework"

for path in (_BACKEND_DIR, _FRAMEWORK_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

__path__ = [str(_BACKEND_APP_DIR)]  # type: ignore[assignment]

from .main import app  # noqa: E402,F401

__all__ = ["app"]
