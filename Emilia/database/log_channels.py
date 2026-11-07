# log channels to monitor your group activities

from Emilia.application import db
from Emilia.database.common import atomic_upsert

log_channels = db.logchannels


async def set_log_db(chat_id, channel_id, channel_title):
    await atomic_upsert(
        log_channels,
        {"chat_id": chat_id},
        {
            "$set": {
                "channel_id": channel_id,
                "channel_title": channel_title,
                "categories": {
                    "settings": True,
                    "admin": True,
                    "user": True,
                    "automated": True,
                    "reports": True,
                    "other": True,
                },
            }
        },
    )
    await _invalidate_log_channel_cache(chat_id)


async def unset_log_db(chat_id):
    await log_channels.delete_one({"chat_id": chat_id})
    await _invalidate_log_channel_cache(chat_id)


async def _invalidate_log_channel_cache(chat_id):
    from Emilia.utils.decorators import invalidate_log_channel_cache

    await invalidate_log_channel_cache(chat_id)


async def get_set_channel(chat_id):
    doc = await log_channels.find_one({"chat_id": chat_id}, {"_id": 0, "channel_title": 1})
    return doc.get("channel_title") if doc else None
