
import asyncio
from sqlalchemy import text
from app.database.connection import engine, async_session_maker
from app.database.base import Base

async def check_connection():
    try:
        # Create tables in the configured database backend.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            print("Successfully created tables.")

        async with async_session_maker() as session:
            result = await session.execute(text("SELECT 1"))
            print("Successfully executed SELECT 1. Result:", result.scalar())
            
    except Exception as e:
        print("Database connection error:", e)

if __name__ == "__main__":
    asyncio.run(check_connection())
