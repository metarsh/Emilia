# warnings a user has recieved in a group chat

from Emilia.application import db
from Emilia.database.common import atomic_upsert, next_sequence
from Emilia.locales import tr

warn_settings = db.warn_settings
user_warnings = db.user_warnings


async def warn_db(chat_id, admin_id, user_id, reason):
    warn_id = await next_sequence(db.counters, f"warn:{chat_id}:{user_id}")
    await user_warnings.insert_one(
        {
            "chat_id": chat_id,
            "user_id": user_id,
            "admin_id": admin_id,
            "reason": reason,
            "warn_id": warn_id,
        }
    )
    return warn_id


async def warn_limit(chat_id):
    warn_data = await warn_settings.find_one({"chat_id": chat_id}, {"_id": 0, "warn_limit": 1})

    if warn_data is not None:
        return warn_data.get("warn_limit", 3)
    else:
        return 3


async def count_user_warn(chat_id, user_id):
    warn_count = await user_warnings.count_documents({"chat_id": chat_id, "user_id": user_id})
    return warn_count


async def remove_warn(chat_id, user_id, warn_id):
    result = await user_warnings.delete_one(
        {"chat_id": chat_id, "user_id": user_id, "warn_id": warn_id}
    )
    return bool(result.deleted_count)


async def set_warn_mode_db(chat_id, warn_mode, time=None):
    await atomic_upsert(
        warn_settings,
        {"chat_id": chat_id},
        {"$set": {"warn_mode": {"warn_mode": warn_mode, "warn_time": time}}},
    )


async def get_warn_mode(chat_id):
    warn_data = await warn_settings.find_one({"chat_id": chat_id}, {"_id": 0, "warn_mode": 1})

    if warn_data is not None and warn_data.get("warn_mode"):
        warn_mode_data = warn_data["warn_mode"]
        warn_mode = warn_mode_data.get("warn_mode", 1)
        warn_mode_time = warn_mode_data.get("warn_time")
        return (warn_mode, warn_mode_time)
    else:
        return (1, None)


async def get_all_warn_reason(chat_id, user_id) -> list:
    warns = user_warnings.find(
        {"chat_id": chat_id, "user_id": user_id}, {"_id": 0, "warn_id": 1, "reason": 1}
    ).sort("warn_id", 1)
    reasons = []
    async for warn in warns:
        warn_id = warn.get("warn_id")
        reason = warn.get("reason") or tr("warnings.reason_wasn_t_given")
        reasons.append(f"{warn_id}. {reason}\n")
    return reasons


async def reset_user_warns(chat_id, user_id):
    await user_warnings.delete_many({"chat_id": chat_id, "user_id": user_id})


async def reset_all_warns_db(chat_id):
    await user_warnings.delete_many({"chat_id": chat_id})


async def set_warn_limit_db(chat_id, warn_limit):
    await atomic_upsert(warn_settings, {"chat_id": chat_id}, {"$set": {"warn_limit": warn_limit}})
