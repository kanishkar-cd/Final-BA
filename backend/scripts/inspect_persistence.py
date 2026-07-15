import asyncio

from sqlalchemy import text

from app.database.connection import engine


async def main() -> None:
    queries = {
        "workflows": "SELECT count(*) FROM workflows WHERE id = 'cd-ai-1'",
        "workflow_states": "SELECT count(*) FROM workflow_states WHERE workflow_id = 'cd-ai-1'",
        "epics": "SELECT count(*) FROM epics WHERE workflow_id = 'cd-ai-1'",
        "user_stories": "SELECT count(*) FROM user_stories WHERE workflow_id = 'cd-ai-1'",
    }
    async with engine.connect() as connection:
        for label, query in queries.items():
            print(label, await connection.scalar(text(query)))
        latest = await connection.scalar(
            text(
                "SELECT state_data FROM workflow_states "
                "WHERE workflow_id = 'cd-ai-1' ORDER BY version DESC LIMIT 1"
            )
        )
        if isinstance(latest, dict):
            print("json_epics", len(latest.get("epics", [])))
            print("json_features", len(latest.get("features", [])))
            print("json_stories", len(latest.get("user_stories", [])))
            print("json_versions", len(latest.get("artifact_versions", [])))
    await engine.dispose()


asyncio.run(main())
