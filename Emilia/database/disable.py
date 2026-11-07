# commands to disable in a group chat

from Emilia.application import db
from Emilia.database.common import atomic_upsert

disable = db.disable


async def set_commands_state(chat_id, commands: list[str], *, disabled: bool):
    if disabled:
        await atomic_upsert(
            disable, {"chat_id": chat_id}, {"$addToSet": {"disabled_items": {"$each": commands}}}
        )
    else:
        await disable.update_one(
            {"chat_id": chat_id}, {"$pull": {"disabled_items": {"$in": commands}}}
        )


async def get_disabled(chat_id) -> list:
    doc = await disable.find_one({"chat_id": chat_id}, {"_id": 0, "disabled_items": 1})
    return doc.get("disabled_items", []) if doc else []


async def disabledel_db(chat_id, disabledel):
    await atomic_upsert(disable, {"chat_id": chat_id}, {"$set": {"disabledel": bool(disabledel)}})


async def get_disabledel(chat_id) -> bool:
    doc = await disable.find_one({"chat_id": chat_id}, {"_id": 0, "disabledel": 1})
    return bool(doc.get("disabledel")) if doc else False
