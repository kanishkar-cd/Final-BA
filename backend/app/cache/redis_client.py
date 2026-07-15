import os
from typing import Optional
import redis.asyncio as redis

class RedisClient:
    _instance: Optional[redis.Redis] = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        if cls._instance is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            cls._instance = redis.from_url(
                redis_url, 
                encoding="utf-8", 
                decode_responses=True,
                max_connections=10,
                socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT_SECONDS", "5")),
                socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT_SECONDS", "5")),
            )
        return cls._instance

    @classmethod
    async def close(cls) -> None:
        if cls._instance is not None:
            await cls._instance.aclose()
            cls._instance = None
