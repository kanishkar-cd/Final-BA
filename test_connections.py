
import asyncio
import os
import sys

# Add backend directory to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "backend")))

async def main():
    print("Testing connections...")
    
    # 1. Test Database Connection
    try:
        from app.database.connection import engine, async_session_maker
        from app.database.base import Base
        import app.database.models  # Import to register models on Base.metadata
        from sqlalchemy import text
        
        print("\n--- Testing Database ---")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            print("Successfully connected to SQLite and created schema tables!")
            
        async with async_session_maker() as session:
            result = await session.execute(text("SELECT 1"))
            print(f"Successfully executed query. Result: {result.scalar()}")
    except Exception as e:
        print("Database connection error:", e)

    # 2. Test Redis Connection
    try:
        from app.cache.redis_client import RedisClient
        import redis.asyncio as redis
        from redis.exceptions import ConnectionError as RedisConnectionError
        
        print("\n--- Testing Redis ---")
        client = RedisClient.get_client()
        await client.ping()
        print("Successfully pinged Redis server at", client.connection_pool.connection_kwargs.get("host", "localhost"))
        
        # Test set/get
        await client.set("test_key", "test_value", ex=10)
        val = await client.get("test_key")
        print(f"Successfully wrote and read from Redis. Value: {val.decode()}")
    except RedisConnectionError as e:
        print("Redis connection error (Server likely not running locally):", e)
    except Exception as e:
        print("Redis error:", e)

if __name__ == "__main__":
    asyncio.run(main())

