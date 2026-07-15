from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """
    Base contract for all backend agents.
    """

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    async def execute(self, payload: InputT) -> OutputT:
        """
        Execute the agent. Falls back to run if not implemented.
        """
        return await self.run(payload)

    async def run(self, *args, **kwargs):
        """
        Backward compatibility.
        Existing agents using run() will continue to work.
        """
        if len(args) > 0:
            return await self.execute(args[0])
        return await self.execute(kwargs.get("payload"))