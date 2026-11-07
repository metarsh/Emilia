from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pyrogram import filters as pyrofilters
from pyrogram.errors import ChatAdminRequired, RPCError

from Emilia.application import LOGGER, db
from Emilia.custom_filter import command, listen
from Emilia.database.common import atomic_find_one_and_update, atomic_upsert
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_user
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.message_actor import actor_id, actor_user

# Configurable default values
DEFAULT_ANTIRAID_DURATION = 6
DEFAULT_RAID_ACTION_TIME = 1
DEFAULT_AUTO_ANTIRAID_THRESHOLD = 20
MAX_JOIN_HISTORY = 1000


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


collection = db.antiraid_data
join_times_collection = db.join_times


@listen(filters=pyrofilters.new_chat_members)
async def on_chat_action(client, message):
    if not message.new_chat_members:
        return

    chat_id = message.chat.id

    # Check if antiraid is enabled for the chat
    antiraid_data = await collection.find_one({"_id": chat_id})
    if antiraid_data and antiraid_data.get("expiry_time", _now()) > _now():
        # Ban the new member if antiraid is enabled
        for new_member in message.new_chat_members:
            try:
                await client.ban_chat_member(
                    chat_id,
                    new_member.id,
                    until_date=_now()
                    + timedelta(
                        hours=antiraid_data.get("raid_action_time", DEFAULT_RAID_ACTION_TIME)
                    ),
                )
            except ChatAdminRequired:
                LOGGER.warning(f"antiraid: lost admin rights in {chat_id}, disabling raid mode")
                await collection.delete_one({"_id": chat_id})
                break
            except (RPCError, OSError) as exc:
                LOGGER.warning(f"antiraid: failed to ban {new_member.id} in {chat_id}: {exc}")
                continue

    elif antiraid_data:
        # Check for automatic antiraid
        auto_antiraid_threshold = antiraid_data.get(
            "auto_antiraid_threshold", DEFAULT_AUTO_ANTIRAID_THRESHOLD
        )
        if auto_antiraid_threshold <= 0:
            return
        current_time = _now()
        one_minute_ago = current_time - timedelta(minutes=1)

        join_times_data = await atomic_find_one_and_update(
            join_times_collection,
            {"chat_id": chat_id},
            [
                {
                    "$set": {
                        "join_times": {
                            "$slice": [
                                {
                                    "$concatArrays": [
                                        {
                                            "$filter": {
                                                "input": {"$ifNull": ["$join_times", []]},
                                                "as": "joined",
                                                "cond": {"$gte": ["$$joined", one_minute_ago]},
                                            }
                                        },
                                        [current_time]
                                        * min(MAX_JOIN_HISTORY, len(message.new_chat_members)),
                                    ]
                                },
                                -MAX_JOIN_HISTORY,
                            ]
                        },
                        "updated_at": current_time,
                    }
                }
            ],
            return_document=ReturnDocument.AFTER,
        )

        if join_times_data:
            recent_join_times = join_times_data.get("join_times", [])

            # If the number of recent join times exceeds the threshold, enable
            # antiraid
            if len(recent_join_times) >= auto_antiraid_threshold:
                # Enable antiraid, honoring an admin-configured duration if set
                duration = antiraid_data.get("antiraid_duration", DEFAULT_ANTIRAID_DURATION)
                expiry_time = current_time + timedelta(hours=duration)
                enabled = await collection.update_one(
                    {
                        "_id": chat_id,
                        "$or": [
                            {"expiry_time": {"$exists": False}},
                            {"expiry_time": {"$lte": current_time}},
                        ],
                    },
                    {"$set": {"expiry_time": expiry_time}},
                )
                if enabled.modified_count:
                    await message.reply_text(
                        tr(
                            "antiraid.auto_anti_raid_enabled_since_users_joined_chat",
                            recent_join_times=len(recent_join_times),
                        )
                    )


@command("antiraid", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def toggle_antiraid(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title
    sender_id = actor_id(message) if actor_user(message) else None
    if not await check_user(
        message, chat_id=chat_id, user_id=sender_id, privileges="can_change_info"
    ):
        return
    antiraid_data = await collection.find_one({"_id": chat_id})
    if antiraid_data and antiraid_data.get("expiry_time", _now()) > _now():
        # Disable antiraid
        await collection.delete_one({"_id": chat_id})
        await message.reply_text(tr("antiraid.antiraid_has_disabled", title=title))
        return "ANTIRAID_DISABLE", None, None
    else:
        # Enable antiraid, honoring an admin-configured duration if set
        duration = (antiraid_data or {}).get("antiraid_duration", DEFAULT_ANTIRAID_DURATION)
        expiry_time = _now() + timedelta(hours=duration)
        await atomic_upsert(collection, {"_id": chat_id}, {"$set": {"expiry_time": expiry_time}})
        await message.reply_text(tr("antiraid.antiraid_has_enabled", title=title))
        return "ANTIRAID_ENABLE", None, None


@command("raidtime", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def set_antiraid_duration(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title
    sender_id = actor_id(message) if actor_user(message) else None
    if not await check_user(
        message, chat_id=chat_id, user_id=sender_id, privileges="can_change_info"
    ):
        return
    try:
        # Extract the duration from the command arguments
        duration = int((message.text or "").split(" ")[1])
        if duration <= 0:
            return await message.reply_text(
                tr("antiraid.invalid_duration_make_sure_it_is_positive")
            )
        await atomic_upsert(collection, {"_id": chat_id}, {"$set": {"antiraid_duration": duration}})
        await message.reply_text(
            tr("antiraid.antiraid_duration_set_hours", duration=duration, title=title)
        )
        return "ANTIRAID_DURATION", None, None
    except (ValueError, IndexError):
        # Invalid or no duration provided, use the default antiraid duration
        await reply_usage(message)


@command("raidactiontime", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def set_raid_action_time(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title
    sender_id = actor_id(message) if actor_user(message) else None
    if not await check_user(
        message, chat_id=chat_id, user_id=sender_id, privileges="can_change_info"
    ):
        return

    try:
        # Extract the time from the command arguments
        time = int((message.text or "").split(" ")[1])
        if time <= 0:
            return await message.reply_text(
                tr("antiraid.invalid_duration_make_sure_it_is_positive")
            )
        await atomic_upsert(collection, {"_id": chat_id}, {"$set": {"raid_action_time": time}})
        await message.reply_text(
            tr("antiraid.raid_action_time_set_hours", duration=time, title=title)
        )
        return "RAID_ACTION_TIME", None, None
    except (ValueError, IndexError):
        # Invalid or no time provided, use the default raid action time
        await reply_usage(message)


@command("autoantiraid", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def set_auto_antiraid(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title
    sender_id = actor_id(message) if actor_user(message) else None
    if not await check_user(
        message, chat_id=chat_id, user_id=sender_id, privileges="can_change_info"
    ):
        return
    try:
        # Extract the threshold from the command arguments
        threshold = (message.text or "").split(" ")[1]
        if threshold.lower() in ["off", "no"]:
            auto_antiraid_threshold = 0
        else:
            auto_antiraid_threshold = int(threshold)
            if not 1 <= auto_antiraid_threshold <= MAX_JOIN_HISTORY:
                await message.reply_text(tr("antiraid.threshold_must_be_a_positive_integer_or"))
                return
    except (ValueError, IndexError):
        # Invalid or no threshold provided, use the default auto antiraid
        # threshold
        auto_antiraid_threshold = DEFAULT_AUTO_ANTIRAID_THRESHOLD

    await atomic_upsert(
        collection, {"_id": chat_id}, {"$set": {"auto_antiraid_threshold": auto_antiraid_threshold}}
    )
    await message.reply_text(
        tr(
            "antiraid.auto_antiraid_threshold_set",
            auto_antiraid_threshold=auto_antiraid_threshold,
            title=title,
        )
    )
    return "AUTO_ANTIRAID", None, None
