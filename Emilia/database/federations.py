# federation module (it connects group chats with one another, so people can manage their multiple groups/commmunities with one federation)

from contextlib import AsyncExitStack

from pymongo.errors import DuplicateKeyError

from Emilia.application import db
from Emilia.config import Config
from Emilia.database.common import atomic_upsert
from Emilia.services.mutations import mutation_claim
from Emilia.utils.tasks import finish_cleanup

feds = db.feds
fbans = db.fbans
fsubs = db.fsubs
fadmins = db.fadmins


async def new_fed(owner_id: int, fed_id, fedname):
    try:
        await feds.insert_one(
            {
                "owner_id": owner_id,
                "fed_id": str(fed_id),
                "fedname": fedname,
                "fedadmins": [],
                "flog": None,
                "chats": [],
                "report": True,
            }
        )
    except DuplicateKeyError:
        if not await feds.find_one({"owner_id": owner_id}, {"_id": 1}):
            raise
        return False
    return True


async def del_fed(fed_id, owner_id):
    async with mutation_claim(db.federation_mutations, fed_id):
        marked = await feds.update_one(
            {"fed_id": fed_id, "owner_id": owner_id}, {"$set": {"deleting": True}}
        )
        if not marked.matched_count:
            return False

        async def cleanup():
            await fbans.delete_many({"fed_id": fed_id})
            await fsubs.delete_many({"fed_id": fed_id})
            await fsubs.update_many(
                {"$or": [{"my_subs": fed_id}, {"fed_subs": fed_id}]},
                {"$pull": {"my_subs": fed_id, "fed_subs": fed_id}},
            )
            removed = await feds.delete_one(
                {"fed_id": fed_id, "owner_id": owner_id, "deleting": True}
            )
            return bool(removed.deleted_count)

        return await finish_cleanup(cleanup())


async def recover_deletions():
    from Emilia.application import LOGGER

    async for doc in feds.find({"deleting": True}, {"fed_id": 1, "owner_id": 1}):
        try:
            await del_fed(doc["fed_id"], doc["owner_id"])
        except Exception:
            LOGGER.exception("Could not finish federation deletion")


async def transfer_fed(fed_id: str, owner_id: int, user_id: int):
    try:
        result = await feds.update_one(
            {
                "fed_id": fed_id,
                "owner_id": owner_id,
                "fedadmins": user_id,
                "deleting": {"$ne": True},
            },
            {"$set": {"owner_id": user_id}, "$pull": {"fedadmins": user_id}},
        )
    except DuplicateKeyError:
        return False
    return bool(result.modified_count)


async def rename_fed(fed_id, fname):
    result = await feds.update_one(
        {"fed_id": fed_id, "deleting": {"$ne": True}}, {"$set": {"fedname": fname}}
    )
    return bool(result.matched_count)


async def chat_join_fed(fed_id, chat_id: int):
    try:
        result = await feds.update_one(
            {"fed_id": fed_id, "deleting": {"$ne": True}}, {"$addToSet": {"chats": chat_id}}
        )
    except DuplicateKeyError:
        return False
    return bool(result.matched_count)


async def user_demote_fed(fed_id, user_id: int):
    # Atomic pull
    await feds.update_one(
        {"fed_id": fed_id, "deleting": {"$ne": True}}, {"$pull": {"fedadmins": user_id}}
    )


async def user_join_fed(fed_id, user_id: int, *, owner_id: int):
    result = await feds.update_one(
        {"fed_id": fed_id, "owner_id": owner_id, "deleting": {"$ne": True}},
        {"$addToSet": {"fedadmins": user_id}},
    )
    return bool(result.matched_count)


async def chat_leave_fed(fed_id, chat_id):
    await feds.update_one(
        {"fed_id": fed_id, "deleting": {"$ne": True}}, {"$pull": {"chats": chat_id}}
    )


async def get_fed_reason(fed_id):
    _fed = await feds.find_one(
        {"fed_id": fed_id, "deleting": {"$ne": True}}, {"_id": 0, "report": 1}
    )
    if _fed is not None:
        return _fed.get("report", True)
    return False


async def set_fed_reason(fed_id, mode):
    await feds.update_one({"fed_id": fed_id, "deleting": {"$ne": True}}, {"$set": {"report": mode}})


async def fban_user(fed_id, user_id: str, firstname, lastname, reason, time: str):
    uid = str(int(user_id))
    entry = [firstname, lastname, reason, time]
    async with mutation_claim(db.federation_mutations, fed_id):
        if not await feds.find_one({"fed_id": fed_id, "deleting": {"$ne": True}}, {"_id": 1}):
            return False
        await atomic_upsert(
            fbans,
            {"fed_id": fed_id},
            {"$set": {f"fbans.{uid}": entry}, "$setOnInsert": {"fed_id": fed_id}},
        )
        return True


async def unfban_user(fed_id, user_id):
    uid = str(int(user_id))
    await fbans.update_one({"fed_id": fed_id}, {"$unset": {f"fbans.{uid}": ""}})


async def get_user_owner_fed_full(owner_id):
    _all_feds = await feds.find_one(
        {"owner_id": owner_id, "deleting": {"$ne": True}}, {"_id": 0, "fed_id": 1, "fedname": 1}
    )
    if _all_feds:
        return _all_feds["fed_id"], _all_feds["fedname"]
    return None


async def search_fed_by_id(fed_id):
    return await feds.find_one({"fed_id": fed_id, "deleting": {"$ne": True}})


async def get_len_fbans(fed_id):
    cursor = await fbans.aggregate(
        [
            {"$match": {"fed_id": fed_id}},
            {"$project": {"count": {"$size": {"$objectToArray": {"$ifNull": ["$fbans", {}]}}}}},
        ]
    )
    rows = await cursor.to_list(length=1)
    return rows[0]["count"] if rows else 0


async def get_all_fbans(fed_id):
    _x_fbans = await fbans.find_one({"fed_id": fed_id}, {"_id": 0, "fbans": 1})
    if _x_fbans:
        return _x_fbans.get("fbans")
    return None


async def get_chat_fed(chat_id: int) -> str | None:
    doc = await feds.find_one(
        {"chats": chat_id, "chats.0": {"$exists": True}, "deleting": {"$ne": True}},
        {"_id": 0, "fed_id": 1},
    )
    if doc and doc.get("fed_id"):
        return doc["fed_id"] or None
    return None


async def get_fban_user(fed_id, user_id: str):
    uid = str(int(user_id))
    _x_data = await fbans.find_one({"fed_id": fed_id}, {"_id": 0, f"fbans.{uid}": 1})
    if _x_data:
        _xx_data = _x_data.get("fbans")
        if _xx_data:
            __xxx_data = _xx_data.get(uid)
            if __xxx_data:
                return True, __xxx_data[2], __xxx_data[3]
    return False, None, None


async def search_user_in_fed(fed_id, user_id: int):
    return (
        await feds.find_one(
            {"fed_id": fed_id, "fedadmins": user_id, "deleting": {"$ne": True}}, {"_id": 1}
        )
        is not None
    )


async def user_feds_report(user_id: int):
    _x = await feds.find_one(
        {"owner_id": user_id, "deleting": {"$ne": True}}, {"_id": 0, "report": 1}
    )
    if _x is not None:
        return _x.get("report", True)
    return True


async def set_feds_setting(user_id: int, mode):
    await feds.update_one(
        {"owner_id": user_id, "deleting": {"$ne": True}}, {"$set": {"report": mode}}
    )


async def get_all_fed_admins(fed_id):
    _fed = await feds.find_one(
        {"fed_id": fed_id, "deleting": {"$ne": True}}, {"_id": 0, "fedadmins": 1, "owner_id": 1}
    )
    if not _fed:
        return []
    x_admins = list(set(_fed.get("fedadmins") or []))
    x_owner = _fed.get("owner_id")
    if x_owner is not None and x_owner not in x_admins:
        x_admins.append(x_owner)
    return x_admins


async def get_fed_log(fed_id):
    _fed = await feds.find_one({"fed_id": fed_id, "deleting": {"$ne": True}}, {"_id": 0, "flog": 1})
    if _fed is not None:
        return _fed.get("flog")
    return False


async def get_all_fed_chats(fed_id):
    _fed = await feds.find_one(
        {"fed_id": fed_id, "deleting": {"$ne": True}}, {"_id": 0, "chats": 1}
    )
    return (_fed or {}).get("chats") or []


async def sub_fed(fed_id: str, my_fed: str):
    async with AsyncExitStack() as stack:
        for identity in sorted({fed_id, my_fed}):
            await stack.enter_async_context(mutation_claim(db.federation_mutations, identity))
            if not await feds.find_one({"fed_id": identity, "deleting": {"$ne": True}}, {"_id": 1}):
                return False
        existing = await fsubs.find_one({"fed_id": my_fed}, {"_id": 0, "my_subs": 1}) or {}
        subscriptions = existing.get("my_subs") or []
        if (
            fed_id not in subscriptions
            and len(subscriptions) >= Config.FEDERATION_MAX_SUBSCRIPTIONS
        ):
            return False
        await atomic_upsert(fsubs, {"fed_id": my_fed}, {"$addToSet": {"my_subs": fed_id}})
    return True


async def unsub_fed(fed_id: str, my_fed: str):
    await fsubs.update_one({"fed_id": my_fed}, {"$pull": {"my_subs": fed_id}})


async def get_my_subs(fed_id):
    x_mysubs = await fsubs.find_one({"fed_id": fed_id}, {"_id": 0, "my_subs": 1})
    if x_mysubs:
        return x_mysubs.get("my_subs") or []
    return []


async def get_fed_subs(fed_id):
    return [doc["fed_id"] async for doc in fsubs.find({"my_subs": fed_id}, {"_id": 0, "fed_id": 1})]


async def add_fname(user_id, fname):
    await atomic_upsert(fadmins, {"user_id": user_id}, {"$set": {"fname": fname}})


async def get_fname(user_id):
    x = await fadmins.find_one({"user_id": user_id}, {"_id": 0, "fname": 1})
    if x:
        return x["fname"]
    return None


async def set_fed_log(fed_id: str, chat_id=None):
    await feds.update_one(
        {"fed_id": fed_id, "deleting": {"$ne": True}}, {"$set": {"flog": chat_id}}
    )


async def quietfed(chat_id: int, argument: bool):
    await atomic_upsert(feds, {"chat_id": chat_id}, {"$set": {"quiet": argument}})


async def get_all_fed_admin(user_id):
    admin = []
    async for x in feds.find(
        {"fedadmins": user_id, "deleting": {"$ne": True}}, {"_id": 0, "fed_id": 1}
    ):
        admin.append(x["fed_id"])

    return admin


async def get_fed_name(fed_id):
    _fed = await feds.find_one(
        {"fed_id": fed_id, "deleting": {"$ne": True}}, {"_id": 0, "fedname": 1}
    )
    if _fed:
        return _fed.get("fedname")
    return None
