import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.services.clone_runtime import _remove_session_files, clone_manager, finish_cleanup

_INSTANCE = secrets.token_hex(16)


def _lease_seconds():
    return max(120, Config.CLONE_START_TIMEOUT + 3 * Config.CLONE_STOP_TIMEOUT + 60)


@asynccontextmanager
async def _mutation_lock(bot_id):
    owner = secrets.token_hex(16)
    now = datetime.now(UTC)
    try:
        claim = await db.clone_operations.find_one_and_update(
            {"_id": bot_id, "expires_at": {"$lte": now}},
            {
                "$set": {
                    "owner": owner,
                    "expires_at": now + timedelta(seconds=max(300, _lease_seconds() * 2)),
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError:
        claim = None
    try:
        yield claim is not None
    finally:
        if claim:
            await finish_cleanup(db.clone_operations.delete_one({"_id": bot_id, "owner": owner}))


async def reserve_slot(bot_id: int, owner_id: int) -> bool:
    current = await db.clone_control.find_one({"_id": "capacity"})
    if current is None:
        entries = [
            {"bot_id": doc["_id"], "owner_id": doc["owner_id"]}
            async for doc in db.clone.find({}, {"owner_id": 1})
            if doc.get("owner_id")
        ]
        try:
            await db.clone_control.update_one(
                {"_id": "capacity"}, {"$setOnInsert": {"bots": entries}}, upsert=True
            )
        except DuplicateKeyError:
            pass
    current = await db.clone_control.find_one({"_id": "capacity"})
    now = datetime.now(UTC)
    for entry in current.get("bots", []):
        created = entry.get("reserved_at")
        if not created or created.replace(tzinfo=UTC) < now - timedelta(seconds=_lease_seconds()):
            if not await db.clone.find_one({"_id": entry["bot_id"]}, {"_id": 1}):
                await db.clone_control.update_one({"_id": "capacity"}, {"$pull": {"bots": entry}})
    current = await db.clone_control.find_one({"_id": "capacity", "bots.bot_id": bot_id})
    if current:
        return any(
            item["bot_id"] == bot_id and item["owner_id"] == owner_id for item in current["bots"]
        )
    balance = await db.clone_slots.find_one({"_id": owner_id})
    limit = Config.CLONES_PER_USER + max(0, int((balance or {}).get("extra", 0)))
    condition = {"_id": "capacity", "bots.bot_id": {"$ne": bot_id}}
    if owner_id not in {*Config.DEV_USERS, Config.OWNER_ID}:
        condition["$expr"] = {
            "$and": [
                {"$lt": [{"$size": "$bots"}, Config.CLONE_LIMIT]},
                {
                    "$lt": [
                        {
                            "$size": {
                                "$filter": {
                                    "input": "$bots",
                                    "as": "bot",
                                    "cond": {"$eq": ["$$bot.owner_id", owner_id]},
                                }
                            }
                        },
                        limit,
                    ]
                },
            ]
        }
    result = await db.clone_control.update_one(
        condition,
        {"$push": {"bots": {"bot_id": bot_id, "owner_id": owner_id, "reserved_at": now}}},
    )
    return bool(result.modified_count)


async def release_slot(bot_id: int) -> None:
    await db.clone_control.update_one({"_id": "capacity"}, {"$pull": {"bots": {"bot_id": bot_id}}})


async def _acquire_lease(bot_id: int, owner_id: int) -> bool:
    now = datetime.now(UTC)
    result = await db.clone.find_one_and_update(
        {
            "_id": bot_id,
            "owner_id": owner_id,
            "$or": [
                {"lease.owner": _INSTANCE},
                {"lease.expires_at": {"$lte": now}},
                {"lease": {"$exists": False}},
            ],
        },
        {
            "$set": {
                "lease": {
                    "owner": _INSTANCE,
                    "expires_at": now + timedelta(seconds=_lease_seconds()),
                }
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return result is not None


async def _rollback(bot_id, previous, *, acquired, token):
    if acquired:
        try:
            await clone_manager._stop_clone(bot_id)
        except Exception:
            await db.clone.update_one(
                {"_id": bot_id, "lease.owner": _INSTANCE},
                {"$set": {"status": "stop_failed"}},
            )
            LOGGER.exception("Clone %s remains tracked after rollback could not stop it", bot_id)
            return
    if previous is None:
        await db.clone.delete_one({"_id": bot_id, "lease.owner": _INSTANCE, "token": token})
        if not await db.clone.find_one({"_id": bot_id}, {"_id": 1}):
            await release_slot(bot_id)
    elif acquired:
        await db.clone.update_one(
            {"_id": bot_id, "lease.owner": _INSTANCE},
            {"$set": {"token": previous["token"], "status": "stopped"}, "$unset": {"lease": ""}},
        )
        if previous["token"] != token:
            _remove_session_files(bot_id)


async def register_clone(
    owner_id: int, token: str, bot_id: int, validator, *, restart=False
) -> tuple[str, str | None, str | None]:
    ok, reason, me = await validator(token)
    if not ok:
        return ("invalid" if reason == "invalid" else "error"), None, None
    if me.id != bot_id or bot_id == int(Config.TOKEN.split(":", 1)[0]):
        return "invalid", None, None
    async with clone_manager.bot_lock(bot_id), _mutation_lock(bot_id) as claimed:
        if not claimed:
            return "busy", None, None
        previous = await db.clone.find_one({"_id": bot_id})
        if previous and previous.get("owner_id") != owner_id:
            return "owned", None, None
        if previous and previous.get("status") == "deleting":
            return "busy", None, None
        acquired = False
        reserved = False
        try:
            if previous:
                acquired = await _acquire_lease(bot_id, owner_id)
                if not acquired:
                    return "busy", None, None
            reserved = await reserve_slot(bot_id, owner_id)
            if not reserved:
                if acquired and bot_id not in clone_manager.clones:
                    await db.clone.update_one(
                        {"_id": bot_id, "lease.owner": _INSTANCE}, {"$unset": {"lease": ""}}
                    )
                return "limit", None, None
            if previous is None:
                now = datetime.now(UTC)
                await db.clone.insert_one(
                    {
                        "_id": bot_id,
                        "owner_id": owner_id,
                        "token": token,
                        "status": "starting",
                        "created_at": now,
                        "lease": {
                            "owner": _INSTANCE,
                            "expires_at": now + timedelta(seconds=_lease_seconds()),
                        },
                    }
                )
                acquired = True
            replacing = previous and previous["token"] != token
            if replacing or restart:
                await clone_manager._stop_clone(bot_id)
                if replacing:
                    _remove_session_files(bot_id)
            result = await db.clone.update_one(
                {"_id": bot_id, "lease.owner": _INSTANCE},
                {"$set": {"token": token, "status": "starting"}},
            )
            if not result.matched_count:
                raise RuntimeError("Clone lease was lost before start")
            success, username, name = await clone_manager._start_clone(owner_id, token, bot_id)
            if not success:
                raise RuntimeError("Clone start failed")
            result = await db.clone.update_one(
                {"_id": bot_id, "lease.owner": _INSTANCE},
                {"$set": {"bot_username": username, "bot_name": name, "status": "running"}},
            )
            if not result.matched_count:
                raise RuntimeError("Clone lease was lost during start")
            return "success", username, name
        except (Exception, asyncio.CancelledError) as exc:
            if previous is None or reserved or acquired:
                await finish_cleanup(_rollback(bot_id, previous, acquired=acquired, token=token))
            if isinstance(exc, asyncio.CancelledError):
                raise
            if isinstance(exc, DuplicateKeyError):
                return "busy", None, None
            LOGGER.exception("Clone registration failed for %s", bot_id)
            return "error", None, None


async def delete_clone(bot_id: int, *, owner_id: int | None = None) -> bool:
    async with clone_manager.bot_lock(bot_id), _mutation_lock(bot_id) as claimed:
        if not claimed:
            return False
        doc = await db.clone.find_one({"_id": bot_id})
        if not doc:
            await release_slot(bot_id)
            return False
        if owner_id is not None and doc.get("owner_id") != owner_id:
            return False
        if not await _acquire_lease(bot_id, doc["owner_id"]):
            return False

        async def cleanup():
            result = await db.clone.update_one(
                {"_id": bot_id, "lease.owner": _INSTANCE},
                {"$set": {"status": "deleting"}},
            )
            if not result.matched_count:
                return False
            await clone_manager._stop_clone(bot_id)
            for collection in (db.users, db.chats):
                await collection.update_many({"bot_ids": bot_id}, {"$pull": {"bot_ids": bot_id}})
            await db.startpic.delete_many({"bot_id": bot_id})
            removed = await db.clone.delete_one({"_id": bot_id, "lease.owner": _INSTANCE})
            if not removed.deleted_count:
                return False
            await release_slot(bot_id)
            _remove_session_files(bot_id)
            return True

        return await finish_cleanup(cleanup())


async def renew_leases_once() -> None:
    ids = list(clone_manager.clones)
    if not ids:
        return
    try:
        await db.clone.update_many(
            {"_id": {"$in": ids}, "lease.owner": _INSTANCE},
            {"$set": {"lease.expires_at": datetime.now(UTC) + timedelta(seconds=_lease_seconds())}},
        )
        held = {
            doc["_id"]
            async for doc in db.clone.find(
                {"_id": {"$in": ids}, "lease.owner": _INSTANCE}, {"_id": 1}
            )
        }
        lost = set(ids) - held
    except Exception:
        LOGGER.exception("Clone lease renewal failed")
        lost = set(ids)

    async def stop_lost(identity):
        try:
            await clone_manager.stop_clone(identity)
        except Exception:
            LOGGER.exception("Could not stop clone %s after lease loss", identity)

    await asyncio.gather(*(stop_lost(identity) for identity in lost))


async def renew_leases() -> None:
    while True:
        await asyncio.sleep(30)
        await renew_leases_once()


async def recover_deletions() -> None:
    async for doc in db.clone.find({"status": "deleting"}, {"_id": 1}):
        try:
            await delete_clone(doc["_id"])
        except Exception:
            LOGGER.exception("Clone deletion recovery failed for %s", doc["_id"])


async def shutdown_clones() -> None:
    try:
        await clone_manager.stop_all_clones()
    finally:
        active = list(clone_manager.clones)
        await db.clone.update_many(
            {"lease.owner": _INSTANCE, "_id": {"$nin": active}, "status": {"$ne": "deleting"}},
            {"$set": {"status": "stopped"}, "$unset": {"lease": ""}},
        )
        await db.clone.update_many(
            {"lease.owner": _INSTANCE, "_id": {"$nin": active}, "status": "deleting"},
            {"$unset": {"lease": ""}},
        )
