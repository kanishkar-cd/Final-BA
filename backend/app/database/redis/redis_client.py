"""Redis connection setup.

This module is intentionally standalone and lives under database/redis so it can
be imported by any future backend without creating backend or API folders.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class RedisSettings:
    url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    socket_timeout_seconds: float = float(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "5"))
    socket_connect_timeout_seconds: float = float(os.getenv("REDIS_CONNECT_TIMEOUT_SECONDS", "5"))
    decode_responses: bool = True


def create_redis_client(settings: RedisSettings | None = None) -> Redis:
    """Create an async Redis client with production-safe timeouts."""
    config = settings or RedisSettings()
    return Redis.from_url(
        config.url,
        socket_timeout=config.socket_timeout_seconds,
        socket_connect_timeout=config.socket_connect_timeout_seconds,
        decode_responses=config.decode_responses,
        health_check_interval=30,
    )
