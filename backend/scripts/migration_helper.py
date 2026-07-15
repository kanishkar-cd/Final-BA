import asyncio
import os
import sys
import logging

# Set up PYTHONPATH equivalent in python so imports like app.* work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config.settings import settings
from app.rag.embedding_service import EmbeddingService
from app.rag.vector_store_service import VectorStoreService
from app.rag.indexing_service import IndexingService
from app.cache.redis_client import RedisClient
from app.schemas.rag import ChunkIndexInput
import asyncpg

# Set up logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration_helper")

async def run_migration():
    logger.info("Starting BGE Base Model Migration & Validation...")

    # 1. Clear Redis cache for embeddings
    logger.info("Connecting to Redis...")
    redis_client = RedisClient.get_client()
    try:
        await redis_client.ping()
        logger.info("Connected to Redis successfully.")
        
        # Clear embedding cache
        keys = await redis_client.keys("rag:embedding:*")
        if keys:
            logger.info(f"Found {len(keys)} cached embeddings. Deleting...")
            await redis_client.delete(*keys)
            logger.info("Redis embedding cache cleared.")
        else:
            logger.info("No cached embeddings found in Redis.")
    except Exception as e:
        logger.warning(f"Could not connect to Redis or clear cache (is Redis running?): {e}")

    # 2. Query document chunks from PostgreSQL
    logger.info("Connecting to PostgreSQL...")
    postgres_dsn = settings.retrieval.postgres_dsn
    db_pool = None
    chunks_input = []
    
    try:
        db_pool = await asyncpg.create_pool(
            dsn=postgres_dsn,
            min_size=1,
            max_size=5,
        )
        logger.info("Connected to PostgreSQL successfully.")
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id::text AS chunk_id, 
                       document_id::text, 
                       project_id::text, 
                       section_title, 
                       context_label, 
                       content, 
                       metadata
                  FROM document_chunks
                 WHERE deleted_at IS NULL
                """
            )
            
            logger.info(f"Fetched {len(rows)} chunks from PostgreSQL.")
            
            for r in rows:
                chunks_input.append(
                    ChunkIndexInput(
                        chunk_id=r["chunk_id"],
                        document_id=r["document_id"],
                        project_id=r["project_id"],
                        content=r["content"],
                        section_title=r["section_title"] or "",
                        context_label=r["context_label"],
                        metadata=dict(r["metadata"]) if r["metadata"] else {},
                    )
                )
    except Exception as e:
        logger.error(f"Error querying PostgreSQL database: {e}")
        logger.info("Aborting migration: PostgreSQL connection/query failed.")
        if db_pool:
            await db_pool.close()
        return

    # 3. Initialize Qdrant and recreate collection
    logger.info("Recreating Qdrant collection...")
    vector_store = VectorStoreService()
    embedding_service = EmbeddingService(redis_client=redis_client)
    indexing_service = IndexingService(
        embedding_service=embedding_service,
        vector_store=vector_store,
        db_pool=db_pool
    )

    try:
        # Recreate collection via Qdrant Client directly to ensure it is fresh
        client = await vector_store._get_client()
        collection_name = vector_store._cfg.collection_name
        
        logger.info(f"Checking for existing collection: {collection_name}")
        existing = await client.get_collections()
        names = {c.name for c in existing.collections}
        
        if collection_name in names:
            logger.info(f"Deleting existing collection: {collection_name}")
            await client.delete_collection(collection_name)
            
        from qdrant_client.http.models import Distance, VectorParams
        logger.info(f"Creating new collection '{collection_name}' with size {settings.qdrant.vector_size}")
        await client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.qdrant.vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Qdrant collection created successfully.")
    except Exception as e:
        logger.error(f"Qdrant collection recreation failed: {e}")
        if db_pool:
            await db_pool.close()
        return

    # 4. Re-embed and re-upload chunks
    if chunks_input:
        logger.info(f"Re-indexing {len(chunks_input)} chunks into Qdrant using {settings.embedding.model_name}...")
        try:
            result = await indexing_service.index_chunks(chunks_input, reindex=True)
            logger.info(f"Indexing completed: {result.indexed_count} indexed, {result.failed_count} failed.")
            
            # 5. Verify vector count matches chunk count
            client = await vector_store._get_client()
            col_info = await client.get_collection(collection_name)
            vector_count = col_info.points_count
            logger.info("Migration validation phase:")
            logger.info(f"Database chunk count: {len(chunks_input)}")
            logger.info(f"Qdrant vector count: {vector_count}")
            
            if vector_count == len(chunks_input):
                logger.info("SUCCESS: Qdrant vector count matches database chunk count!")
            else:
                logger.warning("WARNING: Vector count mismatch! Verify ingestion pipeline.")
        except Exception as e:
            logger.error(f"Indexing failed: {e}")
    else:
        logger.info("No chunks found in database to re-index. Migration completed.")

    if db_pool:
        await db_pool.close()

if __name__ == "__main__":
    asyncio.run(run_migration())
