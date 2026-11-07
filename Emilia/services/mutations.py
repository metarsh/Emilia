import asyncio
import secrets
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from Emilia.utils.tasks import finish_cleanup


@asynccontextmanager
async def mutation_claim(collection, key, *, wait=5, timeout=60):
    owner = secrets.token_hex(16)
    deadline = time.monotonic() + wait
    while True:
        now = datetime.now(UTC)
        try:
            claim = await collection.find_one_and_update(
                {"_id": key, "expires_at": {"$lte": now}},
                {"$set": {"owner": owner, "expires_at": now + timedelta(seconds=timeout + 120)}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        except DuplicateKeyError:
            claim = None
        if claim:
            break
        if time.monotonic() >= deadline:
            raise TimeoutError("Another operation is still changing this record")
        await asyncio.sleep(0.05)
    try:
        async with asyncio.timeout(timeout):
            yield
    finally:
        await finish_cleanup(collection.delete_one({"_id": key, "owner": owner}))
