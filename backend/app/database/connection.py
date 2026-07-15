
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession


load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)


def _async_database_url(url: str) -> str:
    """Select the async SQLAlchemy driver for provider-style PostgreSQL URLs."""
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    # Hosted PostgreSQL URLs commonly use libpq's ``sslmode`` parameter.
    # asyncpg calls the equivalent connection argument ``ssl``.
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        query = [
            ("ssl" if key == "sslmode" else key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key != "channel_binding"
        ]
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return url


DATABASE_URL = _async_database_url(
    os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ba_acc")
)

if not DATABASE_URL.startswith("postgresql+asyncpg://"):
    raise RuntimeError("DATABASE_URL must use PostgreSQL; SQLite runtime storage is not supported.")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)
