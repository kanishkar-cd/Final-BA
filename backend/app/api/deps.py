from __future__ import annotations
from typing import AsyncGenerator
from fastapi import Depends
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session
from app.database.repositories.implementations import WorkflowRepository
from app.cache.redis_client import RedisClient
from app.cache.cache_service import CacheService
from app.cache.cache_manager import CacheManager
from app.orchestrator.user_story_orchestrator import UserStoryOrchestrator
from app.services.workflow_service import WorkflowApiService


def get_redis() -> Redis:
    return RedisClient.get_client()


async def get_cache_manager(redis: Redis = Depends(get_redis)) -> CacheManager:
    return CacheManager(client=redis)


async def get_cache_service(cache_manager: CacheManager = Depends(get_cache_manager)) -> CacheService:
    return CacheService(cache_manager=cache_manager)


async def get_workflow_repository(session: AsyncSession = Depends(get_db_session)) -> WorkflowRepository:
    return WorkflowRepository(session)


async def get_workflow_api_service(
    workflow_repo: WorkflowRepository = Depends(get_workflow_repository),
    cache_service: CacheService = Depends(get_cache_service),
    redis: Redis = Depends(get_redis),
) -> WorkflowApiService:
    return WorkflowApiService(
        workflow_repository=workflow_repo,
        cache_service=cache_service,
        redis_client=redis,
    )


async def get_user_story_orchestrator(
    workflow_api_service: WorkflowApiService = Depends(get_workflow_api_service)
) -> UserStoryOrchestrator:
    return UserStoryOrchestrator(
        workflow_api_service=workflow_api_service,
    )
