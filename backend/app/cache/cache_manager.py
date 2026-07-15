import json
import logging
from typing import Any, Optional, Union
import redis.asyncio as redis
from redis.exceptions import RedisError
from pydantic import BaseModel
from app.cache.redis_client import RedisClient

logger = logging.getLogger(__name__)

class CacheManager:
    """Manages Redis cache operations including JSON serialization and TTLs, with memory fallback."""

    _memory_cache: dict[str, str] = {}

    def __init__(self, client: Optional[redis.Redis] = None):
        self.client = client or RedisClient.get_client()
        self._use_redis = True

    async def get(self, key: str) -> Optional[Any]:
        if self._use_redis:
            try:
                value = await self.client.get(key)
                if value:
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                return None
            except (RedisError, ConnectionError, OSError) as e:
                logger.warning(f"Redis is unavailable, falling back to memory cache: {e}")
                self._use_redis = False

        # Memory fallback
        value = self._memory_cache.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    async def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = 3600  # Default TTL 1 hour
    ) -> bool:
        def json_serial(obj):
            from uuid import UUID
            from datetime import datetime, date
            from pathlib import Path
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            if isinstance(obj, UUID):
                return str(obj)
            if isinstance(obj, Path):
                return str(obj)
            raise TypeError(f"Type {type(obj)} not serializable")

        if isinstance(value, BaseModel):
            serialized_value = value.model_dump_json()
        elif isinstance(value, dict) or isinstance(value, list):
            serialized_value = json.dumps(value, default=json_serial)
        else:
            serialized_value = str(value)
            
        if self._use_redis:
            try:
                return await self.client.set(key, serialized_value, ex=ttl)
            except (RedisError, ConnectionError, OSError) as e:
                logger.warning(f"Redis is unavailable, falling back to memory cache: {e}")
                self._use_redis = False

        self._memory_cache[key] = serialized_value
        return True

    async def delete(self, key: str) -> int:
        if self._use_redis:
            try:
                return await self.client.delete(key)
            except (RedisError, ConnectionError, OSError) as e:
                logger.warning(f"Redis is unavailable, falling back to memory cache: {e}")
                self._use_redis = False

        if key in self._memory_cache:
            del self._memory_cache[key]
            return 1
        return 0
        
    async def delete_pattern(self, pattern: str) -> int:
        if self._use_redis:
            try:
                count = 0
                async for key in self.client.scan_iter(match=pattern):
                    await self.client.delete(key)
                    count += 1
                return count
            except (RedisError, ConnectionError, OSError) as e:
                logger.warning(f"Redis is unavailable, falling back to memory cache: {e}")
                self._use_redis = False

        import fnmatch
        count = 0
        matching_keys = [k for k in self._memory_cache if fnmatch.fnmatch(k, pattern)]
        for k in matching_keys:
            del self._memory_cache[k]
            count += 1
        return count

