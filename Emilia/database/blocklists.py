# blocklists (used to automatically block/filter spam words/phrases)

from pymongo import ReturnDocument

from Emilia.application import db
from Emilia.database.common import atomic_find_one_and_update, atomic_upsert, named_array_update
from Emilia.utils.cache import blocklist_cache

blocklists = db.blocklists
MAX_BLOCKLIST_ENTRIES = 69


async def add_blocklist_db(chat_id, blocklist_text, blocklist_reason) -> bool:
    entry = {"blocklist_text": blocklist_text, "blocklist_reason": blocklist_reason}
    pipeline = named_array_update(
        "blocklist_text",
        "blocklist_text",
        blocklist_text,
        entry,
        max_entries=MAX_BLOCKLIST_ENTRIES,
    )
    pipeline[0]["$set"].update(
        {
            "blocklist_mode": {
                "$ifNull": [
                    "$blocklist_mode",
                    {"$literal": {"blocklist_mode": 1, "blocklist_time": None}},
                ]
            },
            "blocklistdelete": {"$ifNull": ["$blocklistdelete", True]},
            "blocklist_default_reason": {"$ifNull": ["$blocklist_default_reason", None]},
        }
    )
    doc = await atomic_find_one_and_update(
        blocklists,
        {"chat_id": chat_id},
        pipeline,
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "blocklist_text": {"$elemMatch": {"blocklist_text": blocklist_text}}},
    )
    accepted = bool(doc.get("blocklist_text"))
    if accepted:
        await blocklist_cache.delete(f"bl:{chat_id}")
    return accepted


async def rmblocklist_db(chat_id, blocklist_name):
    await blocklists.update_one(
        {"chat_id": chat_id},
        {"$pull": {"blocklist_text": {"blocklist_text": blocklist_name}}},
    )
    await blocklist_cache.delete(f"bl:{chat_id}")


async def unblocklistall_db(chat_id):
    await blocklists.update_one({"chat_id": chat_id}, {"$set": {"blocklist_text": []}})
    await blocklist_cache.delete(f"bl:{chat_id}")


async def get_blocklist(chat_id) -> list:
    key = f"bl:{chat_id}"

    async def load():
        doc = await blocklists.find_one({"chat_id": chat_id}, {"_id": 0, "blocklist_text": 1})
        return doc.get("blocklist_text", []) if doc else []

    return await blocklist_cache.get_or_load(key, load, ttl=180)


async def get_blocklist_reason(chat_id, blocklist_text):
    doc = await blocklists.find_one(
        {"chat_id": chat_id},
        {
            "_id": 0,
            "blocklist_text": {"$elemMatch": {"blocklist_text": blocklist_text}},
        },
    )
    arr = (doc or {}).get("blocklist_text", [])
    if arr:
        return arr[0].get("blocklist_reason")
    return None


async def blocklistMessageDelete(chat_id, blocklistdelete):
    await atomic_upsert(
        blocklists,
        {"chat_id": chat_id},
        {
            "$set": {"blocklistdelete": blocklistdelete},
            "$setOnInsert": {
                "blocklist_text": [],
                "blocklist_mode": {"blocklist_mode": 1, "blocklist_time": None},
                "blocklist_default_reason": None,
            },
        },
    )


async def getblocklistMessageDelete(chat_id) -> bool:
    doc = await blocklists.find_one({"chat_id": chat_id}, {"_id": 0, "blocklistdelete": 1})
    return doc.get("blocklistdelete", True) if doc else True


async def setblocklistmode(chat_id, blocklist_mode, blocklist_time=None):
    await atomic_upsert(
        blocklists,
        {"chat_id": chat_id},
        {
            "$set": {
                "blocklist_mode": {
                    "blocklist_mode": blocklist_mode,
                    "blocklist_time": blocklist_time,
                }
            }
        },
    )


async def getblocklistmode(chat_id):
    doc = await blocklists.find_one(
        {"chat_id": chat_id},
        {"_id": 0, "blocklist_mode": 1, "blocklist_default_reason": 1},
    )
    if doc is not None:
        blocklist_mode = (doc.get("blocklist_mode") or {}).get("blocklist_mode", 1)
        blocklist_time = (doc.get("blocklist_mode") or {}).get("blocklist_time")
        blocklist_default_reason = doc.get("blocklist_default_reason")
        return (blocklist_mode, blocklist_time, blocklist_default_reason)
    else:
        return (1, None, None)


async def setblocklistreason_db(chat_id, reason):
    await atomic_upsert(
        blocklists,
        {"chat_id": chat_id},
        {
            "$set": {"blocklist_default_reason": reason},
            "$setOnInsert": {
                "blocklist_text": [],
                "blocklist_mode": {"blocklist_mode": 1, "blocklist_time": None},
                "blocklistdelete": True,
            },
        },
    )
