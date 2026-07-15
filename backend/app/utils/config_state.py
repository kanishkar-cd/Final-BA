from __future__ import annotations

API_KEY_ERROR: str | None = None


def set_api_key_error(error: str | None) -> None:
    global API_KEY_ERROR
    API_KEY_ERROR = error


def get_api_key_error() -> str | None:
    return API_KEY_ERROR
