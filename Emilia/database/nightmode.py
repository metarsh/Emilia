# nightmode to lock your group chats during nights (12am to 6am)

from Emilia.application import db
from Emilia.database.common import atomic_upsert

nightdb = db.nightmode


async def nightmode_on(chat_id: int):
    return await atomic_upsert(nightdb, {"chat_id": chat_id}, {"$set": {"chat_id": chat_id}})


async def nightmode_off(chat_id: int):
    return await nightdb.delete_one({"chat_id": chat_id})


async def get_nightchats() -> list:
    cursor = nightdb.find(
        {"chat_id": {"$lt": 0}}, {"_id": 0, "chat_id": 1, "original_permissions": 1}
    )
    chats_list = []
    async for doc in cursor:
        chats_list.append(doc)
    return chats_list
