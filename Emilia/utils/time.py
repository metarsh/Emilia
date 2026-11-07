from datetime import UTC, datetime, timedelta

from pyrogram.types import Message

from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage

SECONDS_PER_UNIT = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
UNIT_NAMES = {"m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def convert_time(amount: int, unit: str) -> int:
    return amount * SECONDS_PER_UNIT[unit.lower()]


async def get_time(message, *, argument_index: int | None = None) -> str | None:
    words = (message.text or "").split()
    index = argument_index if argument_index is not None else (1 if message.reply_to_message else 2)
    if len(words) <= index:
        await reply_usage(message)
        return None
    duration = words[index].lower()
    return duration if await check_time(message, duration) else None


async def check_time(message, duration: str) -> bool:
    if not duration:
        await reply_usage(message)
    elif len(duration) == 1:
        await message.reply(
            tr(
                "time.invalid_format",
                arguments=duration,
            )
        )
    elif len(duration) > 10:
        await message.reply(tr("time.duration_too_long"))
    elif not duration[:-1].isascii() or not duration[:-1].isdigit() or int(duration[:-1]) <= 0:
        await message.reply(tr("time.invalid_number", arguments=duration[:-1]))
    elif duration[-1].lower() not in SECONDS_PER_UNIT:
        await message.reply(tr("time.invalid_unit", arguments=duration[-1]))
    elif convert_time(int(duration[:-1]), duration[-1]) >= 366 * SECONDS_PER_UNIT["d"]:
        await message.reply(tr("time.duration_too_long"))
    else:
        return True
    return False


def time_string_helper(duration: str) -> tuple[int, str]:
    return int(duration[:-1]), UNIT_NAMES[duration[-1].lower()]


async def time_converter(message: Message, duration: str) -> datetime | None:
    if not isinstance(duration, str) or not duration:
        await message.reply_text(tr("time.invalid_duration"))
        return None
    if not await check_time(message, duration):
        return None
    return datetime.now(UTC) + timedelta(seconds=convert_time(int(duration[:-1]), duration[-1]))
