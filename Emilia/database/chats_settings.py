# settings related to anonymous admins, playlists, respective to group chats

from Emilia.application import db
from Emilia.database.common import atomic_upsert
from Emilia.utils.cache import anonymous_admin_cache, autoplay_cache, playmenu_cache

chats = db.chats


async def anonadmin_db(chat_id, arg):
    await atomic_upsert(chats, {"chat_id": chat_id}, {"$set": {"anon_admin": arg}})
    # Update cache
    key = f"anon_admin:{chat_id}"
    await anonymous_admin_cache.delete(key)


async def get_anon_setting(chat_id) -> bool:
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "anon_admin": 1})
    return doc.get("anon_admin", False) if doc else False


async def get_anon_setting_cached(chat_id) -> bool:
    key = f"anon_admin:{chat_id}"
    return await anonymous_admin_cache.get_or_load(key, lambda: get_anon_setting(chat_id))


async def playmenu_db(chat_id: int, arg: bool):
    await atomic_upsert(chats, {"chat_id": chat_id}, {"$set": {"playmenu": arg}})
    # Update cache
    key = f"playmenu:{chat_id}"
    await playmenu_cache.delete(key)


async def get_playmenu_setting(chat_id: int) -> bool:
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "playmenu": 1})
    return doc.get("playmenu", False) if doc else False


async def get_playmenu_setting_cached(chat_id: int) -> bool:
    key = f"playmenu:{chat_id}"
    return await playmenu_cache.get_or_load(key, lambda: get_playmenu_setting(chat_id))


async def autoplay_db(chat_id: int, arg: bool):
    await atomic_upsert(chats, {"chat_id": chat_id}, {"$set": {"autoplay": arg}})
    # Update cache
    key = f"autoplay:{chat_id}"
    await autoplay_cache.delete(key)


async def get_autoplay_setting(chat_id: int) -> bool:
    doc = await chats.find_one({"chat_id": chat_id}, {"_id": 0, "autoplay": 1})
    return doc.get("autoplay", False) if doc else False


async def get_autoplay_setting_cached(chat_id: int) -> bool:
    key = f"autoplay:{chat_id}"
    return await autoplay_cache.get_or_load(key, lambda: get_autoplay_setting(chat_id))
