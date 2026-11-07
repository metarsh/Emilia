# your information (/info)

from Emilia.application import db
from Emilia.database.common import atomic_upsert

infodb = db.user_info


async def set_me(user_id: int, info: str):
    return await atomic_upsert(infodb, {"user_id": user_id}, {"$set": {"info": info}})


async def get_me(user_id: int):
    user = await infodb.find_one({"user_id": user_id}, {"_id": 0, "info": 1})
    if user:
        return user.get("info")
    return None


async def set_bio(user_id: int, bio: str):
    return await atomic_upsert(infodb, {"user_id": user_id}, {"$set": {"bio": bio}})


async def get_bio(user_id: int):
    user = await infodb.find_one({"user_id": user_id}, {"_id": 0, "bio": 1})
    if user:
        return user.get("bio")
    return None
