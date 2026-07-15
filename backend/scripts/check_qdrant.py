from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)

from app.rag.vector_store_service import VectorStoreError, VectorStoreService


async def check_qdrant() -> None:
    service = VectorStoreService()
    try:
        await service.ensure_collection()
    except VectorStoreError as exc:
        raise SystemExit(f"Qdrant preflight failed: {exc}") from exc

    print(
        "Qdrant preflight passed: "
        f"collection '{service._cfg.collection_name}' is available via "
        f"{service._endpoint_description()}."
    )


if __name__ == "__main__":
    asyncio.run(check_qdrant())
