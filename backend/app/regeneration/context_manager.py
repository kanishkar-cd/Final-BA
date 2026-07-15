from __future__ import annotations

import json
from typing import Any

from app.schemas.user_story import UserStory, PlanningArtifact
from app.schemas.rag import RetrievedChunkResult


def format_human_comment_to_context(comment: str) -> dict[str, Any]:
    """
    B3.3: Formats a human free-text comment into a structured dict for context injection.
    """
    return {
        "human_feedback": comment,
        "directive": "You MUST incorporate this feedback in the next regeneration."
    }


def assemble_regeneration_context(
    story: UserStory, 
    comment_context: dict[str, Any], 
    retrieved_chunks: list[RetrievedChunkResult]
) -> str:
    """
    B3.1: Regeneration-loop context carry-forward rule.
    Passes last attempt + structured comment + original source chunks.
    Ensures context does not grow unboundedly by omitting history of ALL attempts.
    """
    context_parts = [
        "### PREVIOUS ATTEMPT ###",
        story.model_dump_json(indent=2, exclude={"traceability"}),
        "",
        "### HUMAN FEEDBACK ###",
        json.dumps(comment_context, indent=2),
        "",
        "### ORIGINAL SOURCE MATERIAL ###"
    ]
    
    if not retrieved_chunks:
        context_parts.append("None available.")
    else:
        for c in retrieved_chunks:
            context_parts.append(f"Source [{c.chunk_id}]: {c.content}")
            
    return "\n".join(context_parts)


def scope_epic_refinement_context(
    epic: PlanningArtifact, 
    stories: list[UserStory], 
    retrieved_chunks: list[RetrievedChunkResult]
) -> str:
    """
    B3.2: Epic-only refinement scoping.
    Scopes context to the epic, its linked stories, and linked chunks only.
    Prevents re-running the full PRD through the pipeline.
    """
    context_parts = [
        "### TARGET EPIC ###",
        f"Name: {epic.name}",
        f"Description: {epic.description}",
        "",
        "### LINKED STORIES ###"
    ]
    
    if not stories:
        context_parts.append("No linked stories.")
    else:
        for i, s in enumerate(stories):
            context_parts.append(f"Story {i+1}: {s.user_story}")
            
    context_parts.append("\n### RELEVANT SOURCE MATERIAL ###")
    if not retrieved_chunks:
        context_parts.append("None available.")
    else:
        for c in retrieved_chunks:
            context_parts.append(f"Source [{c.chunk_id}]: {c.content}")
            
    return "\n".join(context_parts)
