import logging
from typing import Any, Optional
from app.cache.cache_manager import CacheManager
from app.cache.cache_keys import CacheKeys

logger = logging.getLogger(__name__)

class CacheService:
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache = cache_manager or CacheManager()

    async def get_document_chunks(self, document_id: str) -> Optional[Any]:
        try:
            key = CacheKeys.doc_chunks(document_id)
            return await self.cache.get(key)
        except Exception as e:
            logger.warning("Cache service error in get_document_chunks: %s", e)
            return None
        
    async def set_document_chunks(self, document_id: str, chunks: Any, ttl: int = 3600) -> bool:
        try:
            key = CacheKeys.doc_chunks(document_id)
            return await self.cache.set(key, chunks, ttl=ttl)
        except Exception as e:
            logger.warning("Cache service error in set_document_chunks: %s", e)
            return False

    async def get_ai_response(self, provider: str, model: str, temperature: float, prompt: str) -> Optional[Any]:
        try:
            key = CacheKeys.ai_response(provider, model, temperature, prompt)
            return await self.cache.get(key)
        except Exception as e:
            logger.warning("Cache service error in get_ai_response: %s", e)
            return None
        
    async def set_ai_response(self, provider: str, model: str, temperature: float, prompt: str, response: Any, ttl: int = 86400) -> bool:
        try:
            key = CacheKeys.ai_response(provider, model, temperature, prompt)
            return await self.cache.set(key, response, ttl=ttl)
        except Exception as e:
            logger.warning("Cache service error in set_ai_response: %s", e)
            return False
        
    async def get_workflow_state(self, workflow_id: str) -> Optional[Any]:
        try:
            key = CacheKeys.generation_state(workflow_id)
            return await self.cache.get(key)
        except Exception as e:
            logger.warning("Cache service error in get_workflow_state: %s", e)
            return None
        
    async def set_workflow_state(self, workflow_id: str, state: Any, ttl: int = 3600) -> bool:
        try:
            key = CacheKeys.generation_state(workflow_id)
            return await self.cache.set(key, state, ttl=ttl)
        except Exception as e:
            logger.warning("Cache service error in set_workflow_state: %s", e)
            return False
        
    async def delete_workflow_state(self, workflow_id: str) -> int:
        try:
            key = CacheKeys.generation_state(workflow_id)
            return await self.cache.delete(key)
        except Exception as e:
            logger.warning("Cache service error in delete_workflow_state: %s", e)
            return 0
        
    async def get_embedding(self, chunk_id: str) -> Optional[Any]:
        try:
            key = CacheKeys.embedding_vectors(chunk_id)
            return await self.cache.get(key)
        except Exception as e:
            logger.warning("Cache service error in get_embedding: %s", e)
            return None
        
    async def set_embedding(self, chunk_id: str, vector: Any, ttl: int = 86400) -> bool:
        try:
            key = CacheKeys.embedding_vectors(chunk_id)
            return await self.cache.set(key, vector, ttl=ttl)
        except Exception as e:
            logger.warning("Cache service error in set_embedding: %s", e)
            return False

    async def get_parsed_document(self, document_hash: str) -> Optional[Any]:
        try:
            key = CacheKeys.doc_hash(document_hash)
            return await self.cache.get(key)
        except Exception as e:
            logger.warning("Cache service error in get_parsed_document: %s", e)
            return None
        
    async def set_parsed_document(self, document_hash: str, parsed_data: Any, ttl: int = 86400) -> bool:
        try:
            key = CacheKeys.doc_hash(document_hash)
            return await self.cache.set(key, parsed_data, ttl=ttl)
        except Exception as e:
            logger.warning("Cache service error in set_parsed_document: %s", e)
            return False
