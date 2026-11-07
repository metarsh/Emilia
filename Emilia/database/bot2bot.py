# bot2bot, whether other bots can use this bot's features or not

from datetime import UTC, datetime, timedelta

from Emilia.application import db
from Emilia.database.common import atomic_upsert

settings = db.bot2bot_settings
pending = db.bot2bot_pending


async def get_bot2bot_settings(chat_id: int):
    doc = await settings.find_one({"chat_id": chat_id}, {"_id": 0, "mode": 1, "skip_review": 1})
    if not doc:
        return {"mode": "off", "skip_review": False}
    return {
        "mode": doc.get("mode", "off"),
        "skip_review": bool(doc.get("skip_review", False)),
    }


async def set_bot2bot_mode(chat_id: int, mode: str):
    await atomic_upsert(
        settings,
        {"chat_id": chat_id},
        {"$set": {"mode": mode}, "$setOnInsert": {"skip_review": False}},
    )


async def set_bot2bot_skip_review(chat_id: int, skip_review: bool):
    await atomic_upsert(
        settings,
        {"chat_id": chat_id},
        {"$set": {"skip_review": skip_review}, "$setOnInsert": {"mode": "off"}},
    )


async def add_pending_bot_command(
    token: str,
    chat_id: int,
    message_id: int,
    bot_id: int,
    client_type: str = "pyrogram",
    command_name: str = None,
    *,
    client_bot_id: int = None,
    review_message_id: int = None,
    source_hash: str = None,
):
    await atomic_upsert(
        pending,
        {"token": token},
        {
            "$set": {
                "token": token,
                "chat_id": chat_id,
                "message_id": message_id,
                "bot_id": bot_id,
                "client_type": client_type,
                "command_name": command_name,
                "client_bot_id": client_bot_id,
                "review_message_id": review_message_id,
                "source_hash": source_hash,
                "expires_at": datetime.now(UTC) + timedelta(minutes=10),
            }
        },
    )


async def consume_pending_bot_command(token, *, chat_id, client_bot_id, review_message_id):
    return await pending.find_one_and_delete(
        {
            "token": token,
            "chat_id": chat_id,
            "client_bot_id": client_bot_id,
            "review_message_id": review_message_id,
            "expires_at": {"$gt": datetime.now(UTC)},
        }
    )
