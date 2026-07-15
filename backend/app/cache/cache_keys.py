import hashlib
import json
from typing import Any, Dict

class CacheKeys:
    """Centralized cache key builder for all 21 cache mechanisms."""

    @staticmethod
    def doc_hash(document_hash: str) -> str:
        return f"doc:hash:{document_hash}"

    @staticmethod
    def parsed_doc(document_id: str) -> str:
        return f"doc:parsed:{document_id}"

    @staticmethod
    def doc_chunks(document_id: str) -> str:
        return f"doc:chunks:{document_id}"

    @staticmethod
    def doc_embeddings(document_id: str) -> str:
        return f"doc:embeddings:{document_id}"

    @staticmethod
    def doc_metadata(document_id: str) -> str:
        return f"doc:meta:{document_id}"

    @staticmethod
    def user_session(session_id: str) -> str:
        return f"session:user:{session_id}"

    @staticmethod
    def workflow_summary(workflow_id: str) -> str:
        return f"workflow:summary:{workflow_id}"

    @staticmethod
    def generation_attempts(workflow_id: str) -> str:
        return f"workflow:attempts:{workflow_id}"

    @staticmethod
    def generation_state(workflow_id: str) -> str:
        return f"workflow:state:{workflow_id}"

    @staticmethod
    def validation_result(story_id: str) -> str:
        return f"validation:result:{story_id}"

    @staticmethod
    def ai_response(provider: str, model: str, temperature: float, prompt: str) -> str:
        # Prompt Hash
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return f"ai:resp:{provider}:{model}:{temperature}:{prompt_hash}"

    @staticmethod
    def iteration_state(workflow_id: str) -> str:
        return f"iteration:state:{workflow_id}"

    @staticmethod
    def confidence_score(story_id: str) -> str:
        return f"confidence:{story_id}"

    @staticmethod
    def review_state(story_id: str) -> str:
        return f"review:state:{story_id}"

    @staticmethod
    def planning_artifacts(workflow_id: str) -> str:
        return f"planning:artifacts:{workflow_id}"

    @staticmethod
    def story_version(story_id: str, version: int) -> str:
        return f"story:version:{story_id}:{version}"

    @staticmethod
    def job_status(job_id: str) -> str:
        return f"job:status:{job_id}"

    @staticmethod
    def embedding_vectors(chunk_id: str) -> str:
        return f"embedding:vectors:{chunk_id}"

    @staticmethod
    def rag_chunk_status(chunk_id: str) -> str:
        return f"rag:chunk_status:{chunk_id}"

    @staticmethod
    def rag_doc_index_status(document_id: str) -> str:
        return f"rag:doc_index:{document_id}"

    @staticmethod
    def rag_project_index_status(project_id: str) -> str:
        return f"rag:project_index:{project_id}"
