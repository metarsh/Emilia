# approval (used to approve trusted users so they can be immune from locks, blocklists and antiflood)

from Emilia.application import db
from Emilia.database.common import atomic_upsert
from Emilia.utils.cache import approvals_cache

approvals = db.approve_d


async def is_approved(chat_id: int, user_id: int, *, fresh: bool = False) -> bool:
    if user_id is None:
        return False

    async def load():
        return (
            await approvals.find_one({"chat_id": chat_id, "user_id": user_id}, {"_id": 1})
            is not None
        )

    if fresh:
        return await load()
    return await approvals_cache.get_or_load(f"appr:{chat_id}:{user_id}", load)


async def approve_user(chat_id: int, user_id: int, name: str):
    await atomic_upsert(
        approvals, {"chat_id": chat_id, "user_id": user_id}, {"$set": {"name": name}}
    )
    await approvals_cache.delete(f"appr:{chat_id}:{user_id}")


async def unapprove_user(chat_id: int, user_id: int) -> bool:
    result = await approvals.delete_one({"chat_id": chat_id, "user_id": user_id})
    await approvals_cache.delete(f"appr:{chat_id}:{user_id}")
    return bool(result.deleted_count)


async def delete_all_approvals(chat_id: int):
    await approvals.delete_many({"chat_id": chat_id})
    await approvals_cache.clear()


def get_approved_users(chat_id: int):
    return approvals.find({"chat_id": chat_id}, {"_id": 0, "user_id": 1, "name": 1})
