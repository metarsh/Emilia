# whether to delete commands (/commands) <- bluetext

from Emilia.application import db
from Emilia.database.common import atomic_upsert
from Emilia.utils.cache import SimpleCache

cleanerdb = db.cleaner
cleancommand_cache = SimpleCache(default_ttl=600, namespace="cleancommand")


async def set_cleancommand(chat_id: int, enable: bool):
    if enable:
        await atomic_upsert(cleanerdb, {"chat_id": chat_id}, {"$set": {"clean_command": True}})
    else:
        await cleanerdb.delete_one({"chat_id": chat_id})
    await cleancommand_cache.delete(f"cleancommand:{chat_id}")


async def get_cleancommand(chat_id: int) -> bool:
    doc = await cleanerdb.find_one(
        {"chat_id": chat_id}, {"_id": 0, "chat_id": 1, "clean_command": 1}
    )
    if doc is None:
        return False
    return doc["clean_command"]


async def get_cleancommand_cached(chat_id: int) -> bool:
    key = f"cleancommand:{chat_id}"
    return await cleancommand_cache.get_or_load(key, lambda: get_cleancommand(chat_id))
