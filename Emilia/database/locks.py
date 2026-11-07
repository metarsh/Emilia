# something you don't want in your groups? use locks to lock them

import asyncio

from Emilia.application import db
from Emilia.database.common import atomic_upsert
from Emilia.utils.cache import cached_db_call, locks_cache

locks = db.locks


async def lock_db(chat_id, lock_item):
    await atomic_upsert(
        locks,
        {"chat_id": chat_id},
        {
            "$setOnInsert": {"chat_id": chat_id, "lockwarns": True, "allow_list": []},
            "$addToSet": {"locked": lock_item},
        },
    )
    await get_locks.invalidate(chat_id)


@cached_db_call(locks_cache, ttl=120)
async def get_locks(chat_id) -> list:
    doc = await locks.find_one({"chat_id": chat_id}, {"_id": 0, "locked": 1})
    return doc.get("locked", []) if doc else []


async def unlock_db(chat_id, locked_item):
    await locks.update_one({"chat_id": chat_id}, {"$pull": {"locked": locked_item}})
    await get_locks.invalidate(chat_id)


@cached_db_call(locks_cache, ttl=300)
async def lockwarns_db(chat_id) -> bool:
    doc = await locks.find_one({"chat_id": chat_id}, {"_id": 0, "lockwarns": 1})
    return doc.get("lockwarns", True) if doc else True


async def set_lockwarn_db(chat_id, warn_args):
    await atomic_upsert(
        locks,
        {"chat_id": chat_id},
        {"$set": {"lockwarns": warn_args}, "$setOnInsert": {"locked": [], "allow_list": []}},
    )
    await lockwarns_db.invalidate(chat_id)


async def allowlist_db(chat_id, allowlist_arg):
    await atomic_upsert(
        locks,
        {"chat_id": chat_id},
        {
            "$setOnInsert": {"chat_id": chat_id, "locked": [], "lockwarns": True},
            "$addToSet": {"allow_list": allowlist_arg},
        },
    )
    await get_allowlist.invalidate(chat_id)


async def rmallow_db(chat_id, allow_arg):
    await locks.update_one({"chat_id": chat_id}, {"$pull": {"allow_list": allow_arg}})
    await get_allowlist.invalidate(chat_id)


async def rmallowall_db(chat_id):
    await locks.update_one({"chat_id": chat_id}, {"$set": {"allow_list": []}})
    await get_allowlist.invalidate(chat_id)


@cached_db_call(locks_cache, ttl=120)
async def get_allowlist(chat_id) -> list:
    doc = await locks.find_one({"chat_id": chat_id}, {"_id": 0, "allow_list": 1})
    return doc.get("allow_list", []) if doc else []


async def invalidate_locks(chat_id):
    await asyncio.gather(
        *(getter.invalidate(chat_id) for getter in (get_locks, get_allowlist, lockwarns_db))
    )
