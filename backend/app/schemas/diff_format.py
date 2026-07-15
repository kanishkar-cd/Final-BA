from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from app.schemas.user_story import UserStory


class DiffField(BaseModel):
    """Represents a single field's difference between versions."""
    field_name: str
    status: Literal["ADDED", "REMOVED", "MODIFIED", "UNCHANGED"]
    old_value: Any | None
    new_value: Any | None


class StoryDiffResult(BaseModel):
    """
    B5.3: Structured before/after diff format.
    Allows NextJS UI to render what changed in a regeneration cleanly.
    """
    story_id: str
    fields: list[DiffField]


def _compare_list(field_name: str, old_list: list[Any], new_list: list[Any]) -> DiffField:
    """Compares two lists of strings or simple objects."""
    if old_list == new_list:
        return DiffField(field_name=field_name, status="UNCHANGED", old_value=old_list, new_value=new_list)
    elif not old_list and new_list:
        return DiffField(field_name=field_name, status="ADDED", old_value=old_list, new_value=new_list)
    elif old_list and not new_list:
        return DiffField(field_name=field_name, status="REMOVED", old_value=old_list, new_value=new_list)
    else:
        return DiffField(field_name=field_name, status="MODIFIED", old_value=old_list, new_value=new_list)


def _compare_scalar(field_name: str, old_val: Any, new_val: Any) -> DiffField:
    if old_val == new_val:
        return DiffField(field_name=field_name, status="UNCHANGED", old_value=old_val, new_value=new_val)
    elif not old_val and new_val:
        return DiffField(field_name=field_name, status="ADDED", old_value=old_val, new_value=new_val)
    elif old_val and not new_val:
        return DiffField(field_name=field_name, status="REMOVED", old_value=old_val, new_value=new_val)
    else:
        return DiffField(field_name=field_name, status="MODIFIED", old_value=old_val, new_value=new_val)


def generate_story_diff(old_story: UserStory, new_story: UserStory) -> StoryDiffResult:
    """
    Compares two UserStory objects and returns a field-level diff.
    Useful for human review UI after a regeneration attempt.
    """
    fields = [
        _compare_scalar("name", old_story.name, new_story.name),
        _compare_scalar("user_story", old_story.user_story, new_story.user_story),
        _compare_scalar("persona", old_story.persona, new_story.persona),
        _compare_scalar("goal", old_story.goal, new_story.goal),
        _compare_scalar("business_value", old_story.business_value, new_story.business_value),
        _compare_scalar("definition_of_done", old_story.definition_of_done, new_story.definition_of_done),
    ]

    # Compare lists
    fields.append(_compare_list("assumptions", old_story.assumptions, new_story.assumptions))
    fields.append(_compare_list("risks", old_story.risks, new_story.risks))

    # Acceptance criteria comparison (comparing descriptions)
    old_ac = [ac.description for ac in old_story.acceptance_criteria]
    new_ac = [ac.description for ac in new_story.acceptance_criteria]
    fields.append(_compare_list("acceptance_criteria", old_ac, new_ac))
    
    # Dependencies comparison
    old_deps = [dep.description for dep in old_story.dependencies]
    new_deps = [dep.description for dep in new_story.dependencies]
    fields.append(_compare_list("dependencies", old_deps, new_deps))

    return StoryDiffResult(
        story_id=new_story.id,
        fields=fields
    )
