from __future__ import annotations

IS_SHUTTING_DOWN = False


def set_shutting_down(value: bool) -> None:
    global IS_SHUTTING_DOWN
    IS_SHUTTING_DOWN = value


def is_shutting_down() -> bool:
    return IS_SHUTTING_DOWN
