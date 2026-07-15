from app.database.connection import DATABASE_URL, _async_database_url


def test_runtime_database_uses_postgresql() -> None:
    assert DATABASE_URL.startswith("postgresql+asyncpg://")


def test_provider_postgresql_url_uses_async_driver() -> None:
    converted = _async_database_url(
        "postgresql://user:password@host/database?sslmode=require&channel_binding=require"
    )
    assert converted.startswith("postgresql+asyncpg://")
    assert "ssl=require" in converted
    assert "channel_binding" not in converted
