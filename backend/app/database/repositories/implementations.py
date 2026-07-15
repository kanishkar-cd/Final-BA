from typing import Optional, List, Any
import uuid
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.base import BaseRepository
from app.database.models import (
    Workflow, WorkflowExecution, WorkflowStateModel,
    Requirement, Epic, Feature, UserStory,
    ValidationResult, Review, AuditLog, LLMExecutionLog
)

class WorkflowRepository(BaseRepository[Workflow]):
    def __init__(self, session: AsyncSession):
        super().__init__(Workflow, session)
        
    async def get_by_document_id(self, document_id: str) -> Optional[Workflow]:
        query = select(self.model).where(self.model.document_id == document_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_with_details(self, id: str) -> Optional[Workflow]:
        query_id = id
        try:
            query_id = uuid.UUID(id)
        except ValueError:
            pass
            
        query = select(self.model).where(self.model.id == query_id).options(
            selectinload(self.model.stories),
            selectinload(self.model.states)
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()


class StoryRepository(BaseRepository[UserStory]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserStory, session)

    async def get_by_workflow_id(self, workflow_id: str) -> List[UserStory]:
        query = select(self.model).where(self.model.workflow_id == workflow_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())


class ValidationRepository(BaseRepository[ValidationResult]):
    def __init__(self, session: AsyncSession):
        super().__init__(ValidationResult, session)


class ReviewRepository(BaseRepository[Review]):
    def __init__(self, session: AsyncSession):
        super().__init__(Review, session)


class AuditRepository(BaseRepository[AuditLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(AuditLog, session)


class LLMExecutionRepository(BaseRepository[LLMExecutionLog]):
    def __init__(self, session: AsyncSession):
        super().__init__(LLMExecutionLog, session)
