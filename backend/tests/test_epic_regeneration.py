from __future__ import annotations

import logging
import sys
from types import ModuleType

import pytest

designlab_core = ModuleType("designlab_core")
designlab_utilities = ModuleType("designlab_core.utilities")
designlab_logger = ModuleType("designlab_core.utilities.logger")
designlab_logger.get_logger = logging.getLogger
sys.modules.setdefault("designlab_core", designlab_core)
sys.modules.setdefault("designlab_core.utilities", designlab_utilities)
sys.modules.setdefault("designlab_core.utilities.logger", designlab_logger)

from app.agents.epic_agent_2 import Epic, EpicGenerationOutput
from app.services.workflow_service import WorkflowApiService


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, **_kwargs) -> bool:
        self.values[key] = value
        return True


class StubEpicAgent:
    def __init__(self, outputs: list[Epic]) -> None:
        self.outputs = outputs
        self.calls = 0

    async def execute(self, _payload) -> EpicGenerationOutput:
        output = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return EpicGenerationOutput(epics=[output.model_copy(deep=True)])


def make_epic(epic_id: str, title: str, story: str, feature: str) -> dict:
    return {
        "id": epic_id,
        "name": title,
        "metadata": {
            "features": [feature],
            "one_line_story": story,
            "priority": "High",
            "dependencies": [],
        },
    }


@pytest.mark.asyncio
async def test_regeneration_retries_once_and_changes_only_selected_epic() -> None:
    original = make_epic("EPIC-001", "Customer Portal", "Original story.", "Account access")
    untouched = make_epic("EPIC-002", "Reporting", "Reporting story.", "View reports")
    identical = Epic(
        epic_id="IGNORED",
        title="Customer Portal",
        features=["Account access"],
        one_line_story="Original story.",
        dependencies=[],
        priority="High",
    )
    improved = identical.model_copy(
        update={
            "title": "Customer Account Experience",
            "one_line_story": "As a customer, I want account access so that I can manage my services.",
        }
    )
    agent = StubEpicAgent([identical, improved])
    service = WorkflowApiService(redis_client=FakeRedis(), epic_agent=agent)
    service._states["WF-1"] = {
        "workflow_id": "WF-1",
        "project_id": "PROJECT-1",
        "epics": [original, untouched],
    }

    regenerated = await service.regenerate_epic("WF-1", "EPIC-001", "Improve wording")

    assert agent.calls == 2
    assert regenerated["id"] == "EPIC-001"
    assert regenerated["name"] == "Customer Account Experience"
    assert regenerated["metadata"]["regeneration_status"] == "regenerated"
    assert service._states["WF-1"]["epics"][1] == untouched


@pytest.mark.asyncio
async def test_regeneration_returns_original_with_metadata_after_one_retry() -> None:
    original = make_epic("EPIC-001", "Customer Portal", "Original story.", "Account access")
    identical = Epic(
        epic_id="EPIC-001",
        title="Customer Portal",
        features=["Account access"],
        one_line_story="Original story.",
        dependencies=[],
        priority="High",
    )
    agent = StubEpicAgent([identical, identical])
    redis = FakeRedis()
    service = WorkflowApiService(redis_client=redis, epic_agent=agent)
    service._states["WF-1"] = {
        "workflow_id": "WF-1",
        "project_id": "PROJECT-1",
        "epics": [original],
    }

    regenerated = await service.regenerate_epic("WF-1", "EPIC-001")

    assert agent.calls == 2
    assert regenerated["name"] == original["name"]
    assert regenerated["metadata"]["one_line_story"] == "Original story."
    assert regenerated["metadata"]["regeneration_status"] == "no meaningful alternative found"
    assert any("EPIC-001" in value for value in map(str, redis.values.values()))
