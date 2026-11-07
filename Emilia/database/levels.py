# levelling system for group chats: XP, rewards, leaderboard etc etc

import math
import secrets
import time

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.database.common import atomic_find_one_and_update, atomic_upsert
from Emilia.services.mutations import mutation_claim

users_collection = db.chatlevels
first_name = db.first_name
level = db.onofflevel


async def award_message_points(user_id, chat_id, multiplier=1.0, *, now=None):
    now = time.time() if now is None else now
    if (
        not isinstance(multiplier, (int, float))
        or not math.isfinite(multiplier)
        or not 0.1 <= multiplier <= 100
    ):
        multiplier = Config.LEVEL_EVENT_MULTIPLIER
    eligible = {
        "$lte": [{"$ifNull": ["$last_message_time", 0]}, now - Config.LEVEL_MESSAGE_COOLDOWN]
    }
    gain = {
        "$multiply": [
            multiplier,
            {"$add": [1, {"$multiply": [0.1, {"$ifNull": ["$prestige", 0]}]}]},
        ]
    }
    previous = await atomic_find_one_and_update(
        users_collection,
        {"user_id": user_id, "chat_id": chat_id},
        [
            {
                "$set": {
                    "points": {
                        "$add": [{"$ifNull": ["$points", 0]}, {"$cond": [eligible, gain, 0]}]
                    },
                    "last_message_time": {"$cond": [eligible, now, "$last_message_time"]},
                }
            }
        ],
        return_document=ReturnDocument.BEFORE,
        projection={"_id": 0, "points": 1, "prestige": 1, "last_message_time": 1},
    )
    if previous and (previous.get("last_message_time") or 0) > now - Config.LEVEL_MESSAGE_COOLDOWN:
        return None
    previous = previous or {}
    old_points = previous.get("points") or 0
    amount = multiplier * (1 + 0.1 * (previous.get("prestige") or 0))
    return {"old_points": old_points, "points": old_points + amount}


def _cooldown(field, now, interval):
    return {"$or": [{field: None}, {field: {"$lte": now - interval}}]}


async def claim_daily(user_id, chat_id, *, now=None):
    now = time.time() if now is None else now
    age = {"$subtract": [now, {"$ifNull": ["$last_date", 0]}]}
    return await users_collection.find_one_and_update(
        {"user_id": user_id, "chat_id": chat_id, **_cooldown("last_date", now, 86400)},
        [
            {
                "$set": {
                    "streak": {
                        "$cond": [
                            {"$and": [{"$gt": [age, 0]}, {"$lt": [age, 172800]}]},
                            {"$add": [{"$ifNull": ["$streak", 0]}, 1]},
                            1,
                        ]
                    }
                }
            },
            {
                "$set": {
                    "points": {
                        "$add": [
                            {"$ifNull": ["$points", 0]},
                            100,
                            {"$min": [{"$multiply": ["$streak", 10]}, 100]},
                        ]
                    },
                    "last_date": now,
                }
            },
        ],
        return_document=ReturnDocument.AFTER,
    )


async def claim_weekly(user_id, chat_id, *, now=None):
    now = time.time() if now is None else now
    return await users_collection.find_one_and_update(
        {
            "user_id": user_id,
            "chat_id": chat_id,
            **_cooldown("last_collection_weekly", now, 7 * 86400),
        },
        [
            {
                "$set": {
                    "points": {"$add": [{"$ifNull": ["$points", 0]}, 500]},
                    "last_collection_weekly": now,
                }
            }
        ],
        return_document=ReturnDocument.AFTER,
    )


async def advance_prestige(user_id, chat_id):
    return await users_collection.find_one_and_update(
        {"user_id": user_id, "chat_id": chat_id, "points": {"$gte": 100000}},
        [{"$set": {"points": 0, "prestige": {"$add": [{"$ifNull": ["$prestige", 0]}, 1]}}}],
        return_document=ReturnDocument.AFTER,
    )


async def _finish_reputation(source):
    grant = source["pending_reputation"]
    applied = {"$ifNull": ["$applied_reputation", []]}
    eligible = {"$not": [{"$in": [{"$literal": grant["id"]}, applied]}]}
    target = {"chat_id": source["chat_id"], "user_id": grant["user_id"]}
    await atomic_upsert(
        users_collection,
        target,
        [
            {
                "$set": {
                    "reputation": {
                        "$add": [{"$ifNull": ["$reputation", 0]}, {"$cond": [eligible, 1, 0]}]
                    },
                    "applied_reputation": {"$setUnion": [applied, {"$literal": [grant["id"]]}]},
                }
            }
        ],
    )
    cleared = await users_collection.update_one(
        {
            "chat_id": source["chat_id"],
            "user_id": source["user_id"],
            "pending_reputation.id": grant["id"],
        },
        {"$unset": {"pending_reputation": ""}},
    )
    if cleared.matched_count:
        await users_collection.update_one(target, {"$pull": {"applied_reputation": grant["id"]}})


async def grant_reputation(user_id, chat_id, target_id, *, now=None):
    now = time.time() if now is None else now
    async with mutation_claim(db.levels_mutations, f"reputation:{chat_id}:{user_id}"):
        source = (
            await users_collection.find_one(
                {"user_id": user_id, "chat_id": chat_id},
                {"user_id": 1, "chat_id": 1, "last_rep_given": 1, "pending_reputation": 1},
            )
            or {}
        )
        if source.get("pending_reputation"):
            await _finish_reputation(source)
        remaining = max(0, 86400 - (now - (source.get("last_rep_given") or 0)))
        if remaining:
            return False, remaining
        grant = {"id": secrets.token_hex(16), "user_id": target_id}
        await atomic_upsert(
            users_collection,
            {"user_id": user_id, "chat_id": chat_id},
            {"$set": {"last_rep_given": now, "pending_reputation": grant}},
        )
        await _finish_reputation(
            {"user_id": user_id, "chat_id": chat_id, "pending_reputation": grant}
        )
        return True, 0


async def recover_reputation():
    async for source in users_collection.find(
        {"pending_reputation": {"$exists": True}}, {"chat_id": 1, "user_id": 1}
    ).batch_size(100):
        try:
            async with mutation_claim(
                db.levels_mutations, f"reputation:{source['chat_id']}:{source['user_id']}"
            ):
                current = await users_collection.find_one(
                    {"_id": source["_id"]}, {"chat_id": 1, "user_id": 1, "pending_reputation": 1}
                )
                if current and current.get("pending_reputation"):
                    await _finish_reputation(current)
        except Exception:
            LOGGER.exception("Could not recover reputation grant")


async def register_name(user_id, name):
    name = name.strip()
    if not name or len(name) > 20:
        raise ValueError("Display names must contain 1 to 20 characters")
    has_name = {
        "$and": [
            {"$eq": [{"$type": "$first_name"}, "string"]},
            {"$ne": ["$first_name", ""]},
        ]
    }
    try:
        previous = await atomic_find_one_and_update(
            first_name,
            {"user_id": user_id},
            [{"$set": {"first_name": {"$cond": [has_name, "$first_name", {"$literal": name}]}}}],
            return_document=ReturnDocument.BEFORE,
            projection={"_id": 0, "first_name": 1},
        )
    except DuplicateKeyError:
        if await first_name.find_one({"first_name": name}, {"_id": 1}):
            return "taken"
        raise
    return (
        "registered"
        if previous and isinstance(previous.get("first_name"), str) and previous["first_name"]
        else "created"
    )
