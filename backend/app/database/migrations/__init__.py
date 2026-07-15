from __future__ import annotations

from typing import Any

from sqlalchemy import DateTime, inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.database.base import Base

# Import the ORM models so all tables are registered on Base.metadata.
from app.database import models as _models  # noqa: F401


async def ensure_database_schema(engine: AsyncEngine) -> None:
    """Create missing ORM tables and apply small, idempotent schema upgrades."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        schema = await conn.run_sync(_schema_snapshot)

        workflow_state_columns = schema.get("workflow_states", {})
        if workflow_state_columns and "version" not in workflow_state_columns:
            await conn.execute(
                text(
                    "ALTER TABLE workflow_states "
                    "ADD COLUMN version INTEGER NOT NULL DEFAULT 1"
                )
            )

        for table_name in ("epics", "features", "user_stories"):
            columns = schema.get(table_name, {})
            if columns and "external_id" not in columns:
                await conn.execute(
                    text(
                        f"ALTER TABLE {table_name} "
                        "ADD COLUMN external_id VARCHAR(255)"
                    )
                )
                await conn.execute(
                    text(
                        f"CREATE INDEX IF NOT EXISTS ix_{table_name}_external_id "
                        f"ON {table_name} (external_id)"
                    )
                )

        if conn.dialect.name == "postgresql":
            await _upgrade_postgres_timestamps(conn, schema)


def _schema_snapshot(sync_conn: Any) -> dict[str, dict[str, Any]]:
    inspector = inspect(sync_conn)
    return {
        table_name: {
            column["name"]: column["type"]
            for column in inspector.get_columns(table_name)
        }
        for table_name in inspector.get_table_names()
    }


async def _upgrade_postgres_timestamps(
    conn: AsyncConnection,
    schema: dict[str, dict[str, Any]],
) -> None:
    """Convert existing naive ORM timestamps to timezone-aware UTC columns."""

    preparer = conn.dialect.identifier_preparer
    for table in Base.metadata.sorted_tables:
        existing_columns = schema.get(table.name)
        if not existing_columns:
            continue

        for column in table.columns:
            existing_type = existing_columns.get(column.name)
            if (
                existing_type is None
                or not isinstance(column.type, DateTime)
                or not column.type.timezone
                or not isinstance(existing_type, DateTime)
                or existing_type.timezone
            ):
                continue

            table_name = preparer.quote(table.name)
            column_name = preparer.quote(column.name)
            await conn.execute(
                text(
                    f"ALTER TABLE {table_name} "
                    f"ALTER COLUMN {column_name} TYPE TIMESTAMP WITH TIME ZONE "
                    f"USING {column_name} AT TIME ZONE 'UTC'"
                )
            )
