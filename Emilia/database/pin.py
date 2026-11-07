# whether your chat should automatically pin messages by linked channel or not

from Emilia.application import db
from Emilia.database.common import atomic_upsert

pin = db.pin


async def cleanlinked_db(chat_id: int, cleanlinked: bool) -> None:
    await atomic_upsert(pin, {"chat_id": chat_id}, {"$set": {"cleanlinked": bool(cleanlinked)}})


async def get_cleanlinked(chat_id: int) -> bool:
    doc = await pin.find_one({"chat_id": chat_id}, {"_id": 0, "cleanlinked": 1})
    return bool(doc.get("cleanlinked")) if doc else False


async def antichannelpin_db(chat_id: int, antichannelpin: bool) -> None:
    await atomic_upsert(
        pin, {"chat_id": chat_id}, {"$set": {"antichannelpin": bool(antichannelpin)}}
    )


async def get_antichannelpin(chat_id: int) -> bool:
    doc = await pin.find_one({"chat_id": chat_id}, {"_id": 0, "antichannelpin": 1})
    return bool(doc.get("antichannelpin")) if doc else False
