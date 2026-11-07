# quotly, create quote like stickers from your own messages

import binascii
import struct
from datetime import UTC, datetime

from pymongo import ReturnDocument
from pyrogram.file_id import FileId, FileType

from Emilia.config import Config
from Emilia.database.common import atomic_find_one_and_update, atomic_upsert


def media_kind(file_id: str) -> str:
    if not isinstance(file_id, str) or not file_id:
        raise ValueError("A quote needs a Telegram media file ID")
    try:
        media = FileId.decode(file_id)
    except (ValueError, TypeError, KeyError, IndexError, struct.error, binascii.Error) as exc:
        raise ValueError("Invalid Telegram media file ID") from exc
    kinds = {FileType.STICKER: "sticker", FileType.PHOTO: "photo", FileType.DOCUMENT: "document"}
    if media.file_type not in kinds:
        raise ValueError("Quotes must be Telegram stickers, photos or image documents")
    return kinds[media.file_type]


async def rating_enabled(database, chat_id: int) -> bool:
    settings = await database.quote_settings.find_one({"_id": chat_id}, {"_id": 0, "rating": 1})
    return bool(settings and settings.get("rating"))


async def set_rating(database, chat_id: int, enabled: bool) -> None:
    await atomic_upsert(database.quote_settings, {"_id": chat_id}, {"$set": {"rating": enabled}})


async def save_quote(database, chat_id: int, bot_id: int, file_id: str):
    kind = media_kind(file_id)
    return await atomic_find_one_and_update(
        database.quotes,
        {"chat_id": chat_id, "bot_id": bot_id, "file_id": file_id},
        {
            "$setOnInsert": {
                "kind": kind,
                "created_at": datetime.now(UTC),
                "upvotes": [],
                "downvotes": [],
                "up_count": 0,
                "down_count": 0,
                "score": 0,
            }
        },
        return_document=ReturnDocument.AFTER,
        projection={"upvotes": 0, "downvotes": 0},
    )


async def top_quotes(database, chat_id: int, bot_id: int, offset: int = 0):
    offset = max(0, int(offset))
    return (
        await database.quotes.find(
            {"chat_id": chat_id, "bot_id": bot_id}, {"upvotes": 0, "downvotes": 0}
        )
        .sort([("score", -1), ("created_at", -1), ("_id", -1)])
        .skip(offset)
        .limit(50)
        .to_list(length=50)
    )


async def random_quote(database, chat_id: int, bot_id: int):
    cursor = await database.quotes.aggregate(
        [
            {"$match": {"chat_id": chat_id, "bot_id": bot_id}},
            {"$sample": {"size": 1}},
            {"$project": {"upvotes": 0, "downvotes": 0}},
        ]
    )
    return next(iter(await cursor.to_list(length=1)), None)


async def vote(database, quote_id, chat_id: int, bot_id: int, user_id: int, choice: int):
    if choice not in {-1, 1}:
        raise ValueError("Quote votes must be -1 or 1")
    selected = "upvotes" if choice == 1 else "downvotes"
    arrays = {name: {"$ifNull": [f"${name}", []]} for name in ("upvotes", "downvotes")}
    updated = {}
    for name, current in arrays.items():
        without_user = {
            "$filter": {
                "input": current,
                "as": "user",
                "cond": {"$ne": ["$$user", user_id]},
            }
        }
        updated[name] = {
            "$cond": [
                {"$in": [user_id, arrays[selected]]},
                without_user,
                {"$concatArrays": [without_user, [user_id]]} if name == selected else without_user,
            ]
        }
    before = await database.quotes.find_one_and_update(
        {
            "_id": quote_id,
            "chat_id": chat_id,
            "bot_id": bot_id,
            "$or": [
                {"upvotes": user_id},
                {"downvotes": user_id},
                {
                    "$expr": {
                        "$lt": [
                            {
                                "$add": [
                                    {"$size": arrays["upvotes"]},
                                    {"$size": arrays["downvotes"]},
                                ]
                            },
                            Config.QUOTE_MAX_VOTERS,
                        ]
                    }
                },
            ],
        },
        [
            {"$set": updated},
            {"$set": {"up_count": {"$size": "$upvotes"}, "down_count": {"$size": "$downvotes"}}},
            {"$set": {"score": {"$subtract": ["$up_count", "$down_count"]}}},
        ],
        return_document=ReturnDocument.BEFORE,
        projection={
            "upvotes": {"$elemMatch": {"$eq": user_id}},
            "downvotes": {"$elemMatch": {"$eq": user_id}},
            "up_count": 1,
            "down_count": 1,
        },
    )
    if before is None:
        return None
    previous = 1 if before.get("upvotes") else (-1 if before.get("downvotes") else 0)
    current = 0 if previous == choice else choice
    return {
        "choice": current,
        "up_count": before.get("up_count", 0) - (previous == 1) + (current == 1),
        "down_count": before.get("down_count", 0) - (previous == -1) + (current == -1),
    }
