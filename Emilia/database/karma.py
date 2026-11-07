# karma helps you get recognition in the group chat, how much respect you have

from pymongo import ReturnDocument

from Emilia.application import db
from Emilia.database.common import atomic_find_one_and_update, atomic_upsert

karmadb = db.karma


users_collection = db.chatlevels


async def increase_points(user_id: int, chat_id: int, points: int) -> int:
    doc = await atomic_find_one_and_update(
        users_collection,
        {"user_id": int(user_id), "chat_id": int(chat_id)},
        [{"$set": {"points": {"$add": [{"$ifNull": ["$points", 0]}, points]}}}],
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "points": 1},
    )
    return doc["points"]


async def user_global_karma(user_id) -> int:
    doc = await users_collection.find_one(
        {"user_id": int(user_id)},
        {"_id": 0, "points": 1},
        sort=[("points", -1)],
    )
    return (doc.get("points") or 0) if doc else 0


async def is_karma_on(chat_id: int) -> bool:
    doc = await karmadb.find_one({"chat_id_toggle": chat_id}, {"_id": 0, "chat_id_toggle": 1})
    return bool(doc)


async def karma_on(chat_id: int):
    await atomic_upsert(karmadb, {"chat_id_toggle": chat_id}, {"$set": {"chat_id_toggle": chat_id}})


async def karma_off(chat_id: int):
    await karmadb.delete_one({"chat_id_toggle": chat_id})
