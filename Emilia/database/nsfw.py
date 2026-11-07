# sometimes we shouldn't talk about somethings

from Emilia.application import db
from Emilia.database.common import atomic_upsert

nsfwdb = db.nsfw


async def is_nsfw_on(chat_id: int) -> bool:
    doc = await nsfwdb.find_one({"chat_id": chat_id}, {"_id": 0, "chat_id": 1})
    return not bool(doc)


async def nsfw_on(chat_id: int):
    return await nsfwdb.delete_one({"chat_id": chat_id})


async def nsfw_off(chat_id: int):
    return await atomic_upsert(nsfwdb, {"chat_id": chat_id}, {"$setOnInsert": {"chat_id": chat_id}})
