import time
from datetime import UTC, datetime

from Emilia.application import db
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.utils.client_context import bot_id
from Emilia.utils.get_user import resolve_target

cache_collection = db.admincache


async def get_user_reason(event, *, allow_chats=False):
    return await resolve_target(event, allow_chats=allow_chats)


async def extract_time(message, time_val):
    parts = (time_val or "").split(maxsplit=1)
    time_val = parts[0] if parts else ""
    if any(time_val.endswith(unit) for unit in ("m", "h", "d")):
        unit = time_val[-1]
        time_num = time_val[:-1]  # type: str
        if (
            len(time_num) > 9
            or not time_num.isascii()
            or not time_num.isdigit()
            or int(time_num) <= 0
        ):
            await message.reply_text(tr("admins.invalid_time_amount_specified"))
            return None
        if unit == "m":
            bantime = int(time.time() + int(time_num) * 60)
        elif unit == "h":
            bantime = int(time.time() + int(time_num) * 60 * 60)
        elif unit == "d":
            bantime = int(time.time() + int(time_num) * 24 * 60 * 60)
        else:
            return
        return bantime
    else:
        return None


def get_time(time: int):
    """Return a human-readable duration string"""
    try:
        t = int(time)
    except (TypeError, ValueError, OverflowError):
        t = 0
    if t < 0:
        t = 0

    if t < 60:
        return f"{t} second{'s' if t != 1 else ''}"

    time_units = [("day", 86400), ("hour", 3600), ("minute", 60)]
    time_parts = []

    for unit, divisor in time_units:
        if t >= divisor:
            count = t // divisor
            t %= divisor
            time_parts.append(f"{count} {unit}{'s' if count != 1 else ''}")

    if t > 0:
        time_parts.append(f"{t} second{'s' if t != 1 else ''}")

    return " ".join(time_parts)


async def update_admin_cache(chat_id, user_id, is_admin, *, client):
    await atomic_upsert(
        cache_collection,
        {"bot_id": bot_id(client), "chat_id": chat_id, "user_id": user_id},
        {"$set": {"is_admin": is_admin, "last_updated": datetime.now(UTC)}},
    )
