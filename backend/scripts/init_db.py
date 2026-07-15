from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv

# Use the same database configuration loaded by app.main when Uvicorn starts.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from app.database.connection import engine
from app.database.migrations import ensure_database_schema


async def init_db() -> None:
    await ensure_database_schema(engine)


if __name__ == "__main__":
    asyncio.run(init_db())
