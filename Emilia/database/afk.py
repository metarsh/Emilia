# away from keyboard (/afk commands)

import time

from Emilia.application import db
from Emilia.database.common import atomic_upsert

afk_collection = db.afk


async def set_afk(user_id: int, first_name="User", reason=None):
    await atomic_upsert(
        afk_collection,
        {"user_id": user_id},
        {"$set": {"first_name": first_name, "reason": reason, "time": time.time()}},
    )


async def unset_afk(user_id):
    await afk_collection.delete_one({"user_id": user_id})


async def is_afk(user_id):
    return bool(await afk_collection.find_one({"user_id": user_id}, {"_id": 1}))


async def get_afk_user(user_id):
    _afk = await afk_collection.find_one({"user_id": user_id})
    return _afk if _afk else None
