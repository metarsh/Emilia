# connection module which helps to connect your group chats with your private chats

import datetime

from Emilia.application import db
from Emilia.database.common import atomic_upsert

connection = db.connection
chats = db.chats


async def get_connection(user_id):
    return await connection.find_one(
        {"user_id": user_id}, {"_id": 0, "connected_chat": 1, "connection": 1}
    )


async def connectDB(user_id, chat_id):
    await atomic_upsert(
        connection, {"user_id": user_id}, {"$set": {"connection": True, "connected_chat": chat_id}}
    )


async def disconnectChat(user_id):
    await atomic_upsert(connection, {"user_id": user_id}, {"$set": {"connection": False}})


async def allow_collection(chat_id, chat_title, allow_collection):
    await atomic_upsert(
        chats,
        {"chat_id": chat_id},
        {
            "$set": {"chat_title": chat_title, "allow_collection": allow_collection},
            "$setOnInsert": {"first_found_date": datetime.datetime.now(datetime.UTC)},
        },
    )


async def get_allow_connection(chat_id) -> bool:
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "allow_collection": 1})
    return doc.get("allow_collection", False) if doc else False
