from __future__ import annotations

from typing import Any
import json

from app.schemas.chunk import Chunk
from app.schemas.rag import RetrievedChunkResult
from app.schemas.user_story import PlanningArtifact, OneLineStoryInput, UserStory


def assemble_segmentation_context(target_chunk: Chunk, neighbor_chunks: list[Chunk]) -> str:
    """
    B1.1: Segmentation Agent context window.
    Provides the target chunk and a small window of neighboring chunks for continuity.
    """
    context_parts = []
    
    # Sort neighbors by chunk_index just in case
    sorted_neighbors = sorted(neighbor_chunks, key=lambda c: c.chunk_index)
    
    context_parts.append("### NEIGHBORING CHUNKS (For Context Only) ###")
    if not sorted_neighbors:
        context_parts.append("None available.")
    else:
        for c in sorted_neighbors:
            prefix = "[PREVIOUS]" if c.chunk_index < target_chunk.chunk_index else "[NEXT]"
            context_parts.append(f"{prefix} Chunk {c.chunk_index}: {c.content}")
            
    context_parts.append("\n### TARGET CHUNK (To be labeled) ###")
    context_parts.append(f"Chunk ID: {str(target_chunk.id)}")
    context_parts.append(f"Content: {target_chunk.content}")
    
    return "\n".join(context_parts)


def assemble_epic_context_rollup(chunks: list[RetrievedChunkResult | Chunk]) -> str:
    """
    B1.2: Epic Agent context roll-up.
    Aggregates multiple related chunks efficiently for Epic generation.
    """
    context_parts = ["### SOURCE MATERIAL ###"]
    
    if not chunks:
        return "No source material available."
        
    for i, c in enumerate(chunks):
        if isinstance(c, RetrievedChunkResult):
            context_parts.append(f"--- Document: {c.document_id} | Section: {c.section_title} ---")
            context_parts.append(f"{c.content}\n")
        else:
            context_parts.append(f"--- Document: {c.document_id} | Section: {c.section_title} ---")
            context_parts.append(f"{c.content}\n")
            
    return "\n".join(context_parts)


def assemble_user_story_context(
    epic: PlanningArtifact, 
    one_line_story: OneLineStoryInput, 
    retrieved_chunks: list[RetrievedChunkResult]
) -> str:
    """
    B1.3: User Stories Agent context scoping.
    Provides parent epic summary, specific one-line goal, and relevant chunks.
    """
    context_parts = [
        "### PARENT EPIC ###",
        f"Name: {epic.name}",
        f"Description: {epic.description}",
        "",
        "### STORY GOAL ###",
        f"Feature ID: {one_line_story.feature_id}",
        f"Description: {one_line_story.description}",
        "",
        "### RELEVANT SOURCE MATERIAL ###"
    ]
    
    if not retrieved_chunks:
        context_parts.append("No source material available.")
    else:
        for c in retrieved_chunks:
            context_parts.append(f"Source [{c.chunk_id}]: {c.content}")
            
    return "\n".join(context_parts)


def assemble_validation_context(story: UserStory, retrieved_chunks: list[RetrievedChunkResult]) -> str:
    """
    B1.4: Validation Agent context scoping.
    Candidate output plus cited source chunks only.
    """
    context_parts = [
        "### CANDIDATE USER STORY ###",
        story.model_dump_json(indent=2),
        "",
        "### CITED SOURCE MATERIAL ###"
    ]
    
    if not retrieved_chunks:
        context_parts.append("None provided.")
    else:
        for c in retrieved_chunks:
            context_parts.append(f"Source [{c.chunk_id}]: {c.content}")
            
    return "\n".join(context_parts)
