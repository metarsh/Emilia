# auto approve members on join request

from Emilia.application import db
from Emilia.database.common import atomic_upsert
from Emilia.utils.cache import SimpleCache

collection = db.autoapprove
cache = SimpleCache(default_ttl=3600, namespace="autoapprove")


async def get_autoapprove_mode(chat_id: int) -> str:
    async def load():
        result = await collection.find_one({"chat_id": chat_id}, {"_id": 0, "mode": 1})
        return result.get("mode", "off") if result else "off"

    return await cache.get_or_load(chat_id, load)


async def set_autoapprove_mode(chat_id: int, mode: str):
    await atomic_upsert(collection, {"chat_id": chat_id}, {"$set": {"mode": mode}})
    await cache.delete(chat_id)
