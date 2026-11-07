from pyrogram import Client, filters
from pyrogram.errors import RPCError
from pyrogram.types import Message

from Emilia.application import LOGGER, db
from Emilia.custom_filter import command
from Emilia.database.approval import is_approved
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.services.flood_tracker import MAX_HISTORY, MAX_WINDOW, finish_detection, record_message
from Emilia.utils.cache import SimpleCache
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import bot_has_permission, is_user_admin
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.restrictions import restrict_member
from Emilia.utils.tasks import finish_cleanup
from Emilia.utils.time import check_time, time_converter

DB = db.antiflood_chats
_flood_status_cache = SimpleCache(default_ttl=60, namespace="antiflood_status")
_settings_cache = SimpleCache(default_ttl=300, namespace="antiflood_settings")


async def flood_limits(chat_id: int):
    """Return the cached limits, punishment, deletion setting and timer mode."""
    cache_key = f"antiflood_settings:{chat_id}"

    # Try Cache (L1 + L2)
    cached_data = await _settings_cache.get(cache_key)
    if cached_data:
        return cached_data

    # Fetch from Mongo (L3)
    limit = await DB.find_one({"chat_id": chat_id})
    if not limit:
        # Default values. timed_on is False by default if not set.
        result = (10, 10, 10, "ban", "yes", None, False)
    else:
        chat_limit = int(limit.get("limit", 10))
        timed_limit = int(limit.get("timed_limit", 10))
        timed_duration = int(limit.get("timed_duration", 10))
        action = limit.get("action", "ban")
        clear_flood = limit.get("clear", "yes")
        timed_on = limit.get("timed_status", "off") == "on"

        duration = limit.get("time") if action in {"tban", "tmute"} else None
        result = (chat_limit, timed_limit, timed_duration, action, clear_flood, duration, timed_on)

    # Set Cache
    await _settings_cache.set(cache_key, result, ttl=300)
    return result


async def _check_flood_on_cached(chat_id: int) -> bool:
    k = f"flood_on:{chat_id}"
    v = await _flood_status_cache.get(k)
    if v is not None:
        return v
    settings = await DB.find_one({"chat_id": chat_id})
    on = bool(settings and "status" in settings and settings["status"] != "off")
    await _flood_status_cache.set(k, on, ttl=60)
    return on


async def check_flood_on(chat_id: int):
    settings = await DB.find_one({"chat_id": chat_id})
    return bool(settings and "status" in settings and settings["status"] != "off")


@command("setfloodtimer", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def setfloodtimer(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    arguments = message.text.split()[1:]
    if not arguments:
        return await reply_usage(message, setfloodtimer)

    if arguments[0].lower() in {"off", "no"} and len(arguments) == 1:
        await atomic_upsert(DB, {"chat_id": chat_id}, {"$set": {"timed_status": "off"}})
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await message.reply(tr("antiflood.timed_antiflood_is_now_disabled"))
        return "DISABLED_TIMED_ANTIFLOOD", None, None

    if len(arguments) != 2 or not all(
        argument.isascii() and argument.isdigit() for argument in arguments
    ):
        return await reply_usage(message)
    count, duration = map(int, arguments)
    if not 1 <= count <= MAX_HISTORY or not 1 <= duration <= MAX_WINDOW:
        return await message.reply(
            tr("antiflood.timer_bounds", count=MAX_HISTORY, seconds=MAX_WINDOW)
        )

    if not (
        (
            await bot_has_permission(
                message, chat_id=chat_id, privileges="can_restrict_members", silent=True
            )
        )
        and (
            await bot_has_permission(
                message, chat_id=chat_id, privileges="can_delete_messages", silent=True
            )
        )
    ):
        await atomic_upsert(DB, {"chat_id": chat_id}, {"$set": {"status": "off"}})
        # Invalidate Settings Cache
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)

        await message.reply(tr("antiflood.permissions_missing"))
        return

    await atomic_upsert(
        DB,
        {"chat_id": chat_id},
        {
            "$set": {
                "timed_limit": count,
                "timed_duration": duration,
                "timed_status": "on",
            }
        },
    )
    # Invalidate Settings Cache
    await _settings_cache.delete(f"antiflood_settings:{chat_id}")

    await message.reply(
        tr("antiflood.timed_antiflood_is_now_set_to_trigger", count=count, duration=duration)
    )
    return "SET_TIMED_ANTIFLOOD", None, None


@command("flood", chat_scope="group", allow_connected=True)
async def flood_func(client, message: Message):
    chat_id = effective_chat_id(message)

    if not await check_flood_on(chat_id):
        await message.reply_text(tr("antiflood.antiflood_is_disabled_in_this_chat"))
    else:
        # Note: Unpacking 7 values now
        (
            limit,
            timed_limit,
            timed_duration,
            action,
            clear_flood,
            time,
            timed_on,
        ) = await flood_limits(chat_id)
        if time:
            return await message.reply_text(
                tr(
                    "antiflood.timed_punishment_settings",
                    limit=limit,
                    action=action,
                    duration=time,
                    clear_flood=clear_flood,
                    timed_limit=timed_limit,
                    timed_duration=timed_duration,
                )
            )
        await message.reply_text(
            tr(
                "antiflood.settings",
                limit=limit,
                action=action,
                clear_flood=clear_flood,
                timed_limit=timed_limit,
                timed_duration=timed_duration,
            )
        )


@command(["antiflood", "setflood"], chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def antiflood_func(client, message: Message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    if len(message.text.split()) < 2:
        return await reply_usage(message, antiflood_func)

    if not (
        (
            await bot_has_permission(
                message, chat_id=chat_id, privileges="can_restrict_members", silent=True
            )
        )
        and (
            await bot_has_permission(
                message, chat_id=chat_id, privileges="can_delete_messages", silent=True
            )
        )
    ):
        await atomic_upsert(DB, {"chat_id": chat_id}, {"$set": {"status": "off"}})
        # Invalidate Cache
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)

        await message.reply(tr("antiflood.permissions_missing_disabled"))
        return

    status = message.text.split(None, 1)[1].strip()

    if status == "on":
        await atomic_upsert(DB, {"chat_id": chat_id}, {"$set": {"status": "on"}})
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", True, ttl=60)
        await message.reply(tr("antiflood.antiflood_is_now_enabled_in_this_chat"))
        return "ENABLED_ANTIFLOOD", None, None
    elif status == "off" or status == "no":
        await atomic_upsert(DB, {"chat_id": chat_id}, {"$set": {"status": "off"}})
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)
        await message.reply(tr("antiflood.antiflood_is_now_disabled_in_this_chat"))
        return "DISABLED_ANTIFLOOD", None, None
    elif status.isdigit():
        status = int(status)
        if status < 1 or status > 50:
            await message.reply(tr("antiflood.flood_value_should_be_between_1_and"))
        else:
            await atomic_upsert(
                DB,
                {"chat_id": chat_id},
                {"$set": {"limit": status, "status": "on"}},
            )
            await _settings_cache.delete(f"antiflood_settings:{chat_id}")
            await _flood_status_cache.set(f"flood_on:{chat_id}", True, ttl=60)
            await message.reply(tr("antiflood.antiflood_limit_now_set_chat", status=status))
            return "NEW_FLOOD_LIMIT", None, None
    else:
        await reply_usage(message)


@command(["floodmode", "setfloodmode"], chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def floodmode(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    if len(message.text.split()) < 2:
        return await reply_usage(message, floodmode)

    if not (
        (
            await bot_has_permission(
                message, chat_id=chat_id, privileges="can_restrict_members", silent=True
            )
        )
        and (
            await bot_has_permission(
                message, chat_id=chat_id, privileges="can_delete_messages", silent=True
            )
        )
    ):
        await atomic_upsert(DB, {"chat_id": chat_id}, {"$set": {"status": "off"}})
        # Invalidate Cache
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)

        await message.reply(tr("antiflood.permissions_missing"))
        return

    action = message.text.split()[1]
    if action not in ["ban", "mute", "kick", "tban", "tmute"]:
        return await message.reply(tr("antiflood.invalid_action_type_choose_from_ban_mute"))
    if action in ["tban", "tmute"]:
        try:
            time = message.text.split()[2]
        except IndexError:
            time = message.text.split()[-1]
        if await check_time(message, time):
            await atomic_upsert(
                DB,
                {"chat_id": chat_id},
                {"$set": {"action": action, "time": time}},
            )
            # Invalidate Cache
            await _settings_cache.delete(f"antiflood_settings:{chat_id}")

            await message.reply(
                tr("antiflood.action_take_flooding_users_now_set", action=action, duration=time)
            )
            return "SET_FLOOD_ACTION", None, None
        else:
            return

    await atomic_upsert(
        DB,
        {"chat_id": chat_id},
        {"$set": {"action": action}},
    )
    # Invalidate Cache
    await _settings_cache.delete(f"antiflood_settings:{chat_id}")

    await message.reply(tr("antiflood.action_to_take_on_flooding_users_is", action=action))
    return "SET_FLOOD_ACTION", None, None


@command("clearflood", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def clearflood(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    if len(message.text.split()) < 2:
        return await reply_usage(message, clearflood)

    if not (
        (
            await bot_has_permission(
                message, chat_id=chat_id, privileges="can_restrict_members", silent=True
            )
        )
        and (
            await bot_has_permission(
                message, chat_id=chat_id, privileges="can_delete_messages", silent=True
            )
        )
    ):
        await atomic_upsert(DB, {"chat_id": chat_id}, {"$set": {"status": "off"}})
        # Invalidate Cache
        await _settings_cache.delete(f"antiflood_settings:{chat_id}")
        await _flood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)

        await message.reply(tr("antiflood.permissions_missing"))
        return

    action = message.text.split()[1]
    if action not in ["yes", "no", "on", "off"]:
        return await message.reply(tr("antiflood.invalid_action_type_choose_from_yes_no"))

    await atomic_upsert(
        DB,
        {"chat_id": chat_id},
        {"$set": {"clear": action}},
    )
    # Invalidate Cache
    await _settings_cache.delete(f"antiflood_settings:{chat_id}")

    await message.reply(tr("antiflood.clear_flood_messages_is_now_set_to", action=action))
    return "SET_CLEAR_FLOOD", None, None


async def _punish_flood(client, message, action, duration):
    chat_id, user_id = message.chat.id, message.from_user.id
    values = {"user_name": message.from_user.first_name}
    if action == "ban":
        await client.ban_chat_member(chat_id, user_id)
        key = "antiflood.has_banned_spamming"
    elif action == "kick":
        await client.ban_chat_member(chat_id, user_id)
        await client.unban_chat_member(chat_id, user_id)
        key = "antiflood.has_kicked_spamming"
    elif action == "mute":
        await restrict_member(chat_id, user_id, client=client)
        key = "antiflood.has_muted_spamming"
    elif action in {"tban", "tmute"}:
        until = await time_converter(message, duration)
        if until is None:
            raise ValueError("Invalid temporary flood punishment duration")
        values["duration"] = duration
        if action == "tban":
            await client.ban_chat_member(chat_id, user_id, until_date=until)
            key = "antiflood.has_temporarily_banned_spamming"
        else:
            await restrict_member(
                chat_id, user_id, until_date=int(until.timestamp()), client=client
            )
            key = "antiflood.has_temporarily_muted_spamming"
    else:
        raise ValueError("Invalid flood punishment action")
    return tr(key, **values)


@Client.on_message(
    filters.group
    & ~filters.new_chat_members
    & ~filters.left_chat_member
    & ~filters.service
    & ~filters.bot,
    group=11,
)
async def handle_message(client, message):
    if not message.from_user or not await _check_flood_on_cached(message.chat.id):
        return
    chat_id, user_id = message.chat.id, message.from_user.id
    limit, timed_limit, window, action, clear_flood, duration, timed = await flood_limits(chat_id)
    exempt = await is_approved(chat_id, user_id) or await is_user_admin(message, silent=True)
    detection = await record_message(
        client,
        chat_id,
        user_id,
        message.id,
        threshold=int(timed_limit if timed else limit),
        window=int(window),
        timed=timed,
        exempt=exempt,
    )
    if detection is None:
        return
    succeeded = False
    try:
        notice = await _punish_flood(client, message, action, duration)
        succeeded = True
        await client.send_message(chat_id, notice)
        if clear_flood in {"yes", "on"}:
            try:
                await client.delete_messages(chat_id, detection.message_ids)
            except (RPCError, OSError):
                LOGGER.debug("Could not delete flood messages in %s", chat_id, exc_info=True)
    finally:
        await finish_cleanup(finish_detection(detection, succeeded=succeeded))
