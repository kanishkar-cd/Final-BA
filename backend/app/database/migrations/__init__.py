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

        if conn.dialect.name == "postgresql" and "document_chunks" not in schema:
            await _install_rag_schema(conn)
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


async def _install_rag_schema(conn: AsyncConnection) -> None:
    """Install the standalone chunk table required by the RAG services."""

    raw_connection = await conn.get_raw_connection()
    driver_connection = raw_connection.driver_connection
    await driver_connection.execute(
        """
        CREATE TABLE IF NOT EXISTS document_chunks (
            id UUID PRIMARY KEY,
            document_id UUID NOT NULL,
            project_id UUID NOT NULL,
            chunk_index INTEGER NOT NULL DEFAULT 0,
            section_title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL,
            token_count INTEGER,
            content_hash TEXT,
            context_label TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            content_tsv TSVECTOR,
            embedding_indexed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ
        );

        CREATE OR REPLACE FUNCTION document_chunks_tsv_update()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.content_tsv := to_tsvector(
                'english', coalesce(NEW.section_title, '') || ' ' || coalesce(NEW.content, '')
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        DROP TRIGGER IF EXISTS trg_document_chunks_tsv ON document_chunks;
        CREATE TRIGGER trg_document_chunks_tsv
            BEFORE INSERT OR UPDATE OF section_title, content ON document_chunks
            FOR EACH ROW EXECUTE FUNCTION document_chunks_tsv_update();

        CREATE INDEX IF NOT EXISTS idx_document_chunks_content_fts
            ON document_chunks USING gin (content_tsv) WHERE deleted_at IS NULL;

        CREATE OR REPLACE FUNCTION rag_tsquery(query_text TEXT)
        RETURNS tsquery AS $$
        BEGIN
            RETURN websearch_to_tsquery('english', query_text);
        END;
        $$ LANGUAGE plpgsql IMMUTABLE;
        """
    )


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
