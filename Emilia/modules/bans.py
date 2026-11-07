import html
import time
from datetime import UTC, datetime

from pyrogram import filters as pyrofilters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import MessageDeleteForbidden, RPCError
from pyrogram.types import (
    Chat,
    ReplyParameters,
)
from redis.exceptions import RedisError

from Emilia.application import LOGGER
from Emilia.application import db as xdb
from Emilia.custom_filter import command, listen
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.utils.admins import extract_time, get_time, get_user_reason
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import bot_has_permission, can_restrict_member, check_user
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.get_user import mention_html
from Emilia.utils.linked_chat import get_linked_channel
from Emilia.utils.message_actor import actor_id as sender_id
from Emilia.utils.message_actor import actor_name


def _is_group(message):
    return effective_chat(message).type in (ChatType.GROUP, ChatType.SUPERGROUP)


@log_to_channel
async def execute_operation(
    client,
    event,
    user_id,
    name,
    mode,
    reason="",
    tt=0,
    reply_to=None,
    cb=False,
    actor_id=777000,
    actor="Anonymous",
):
    if reply_to == event.id:
        reply_to = event.reply_to_message_id or event.id
    r = ""
    if reason:
        # Use expandable blockquote for the reason
        r = tr("bans.execute_operation_reason", reason=html.escape(reason))

    actor_html = mention_html(actor_id, actor, client=client)
    target_html = mention_html(user_id, name, client=client)

    if not await bot_has_permission(event, privileges="can_restrict_members"):
        return
    if mode in {"dban", "dkick"} and event.reply_to_message_id:
        if not await bot_has_permission(event, privileges="can_delete_messages"):
            return
        try:
            await client.delete_messages(event.chat.id, event.reply_to_message_id)
        except MessageDeleteForbidden:
            return await event.reply_text(tr("bans.i_cannot_delete_one_of_the_messages"))

    if mode in ["ban", "dban"]:
        await client.ban_chat_member(effective_chat_id(event), int(user_id))

        if cb:
            await event.delete()
            reply_to = None
        await client.send_message(
            event.chat.id,
            tr(
                "bans.yep_has_banned",
                target_html=target_html,
                actor_html=actor_html,
                yep_has_banned=r,
            ),
            parse_mode=ParseMode.HTML,
            reply_parameters=ReplyParameters(message_id=reply_to) if reply_to else None,
        )
        return "BAN", user_id, name

    elif mode in ["kick", "dkick"]:
        await client.ban_chat_member(effective_chat_id(event), int(user_id))
        await client.unban_chat_member(effective_chat_id(event), int(user_id))

        if cb:
            await event.delete()
            reply_to = None
        await client.send_message(
            event.chat.id,
            tr(
                "bans.yep_has_kicked",
                target_html=target_html,
                actor_html=actor_html,
                yep_has_kicked=r,
            ),
            parse_mode=ParseMode.HTML,
            reply_parameters=ReplyParameters(message_id=reply_to) if reply_to else None,
        )
        return "KICK", user_id, name

    elif mode == "tban":
        if cb:
            await event.delete()
            reply_to = None
        await client.ban_chat_member(
            effective_chat_id(event),
            int(user_id),
            until_date=datetime.fromtimestamp(int(tt), UTC),
        )
        duration_text = get_time(max(0, int(tt) - int(time.time())))
        await client.send_message(
            event.chat.id,
            tr(
                "bans.yep_has_temporarily_banned",
                target_html=target_html,
                duration_text=duration_text,
                actor_html=actor_html,
                yep_has_temporarily=r,
            ),
            parse_mode=ParseMode.HTML,
            reply_parameters=ReplyParameters(message_id=reply_to) if reply_to else None,
        )
        return "TEMP_BAN", user_id, name

    elif mode == "unban":
        if cb:
            await event.delete()
            reply_to = None
        await client.unban_chat_member(effective_chat_id(event), int(user_id))

        await client.send_message(
            event.chat.id,
            tr(
                "bans.yep_can_join_group_again_they_were_unbanned",
                target_html=target_html,
                actor_html=actor_html,
            ),
            reply_parameters=ReplyParameters(message_id=reply_to) if reply_to else None,
            parse_mode=ParseMode.HTML,
        )
        return "UNBAN", user_id, name

    elif mode == "sban":
        await client.ban_chat_member(effective_chat_id(event), int(user_id))

    elif mode == "skick":
        await client.ban_chat_member(effective_chat_id(event), int(user_id))
        await client.unban_chat_member(effective_chat_id(event), int(user_id))


async def _ban_target(client, event, mode):
    user, reason = await get_user_reason(event, allow_chats=True)
    if not user:
        await event.reply_text(tr("errors.user_not_found"))
        return None
    if isinstance(user, Chat):
        if user.id == effective_chat_id(event):
            await event.reply_text(tr("bans.cannot_perform_this_command_on_anonymous_admins"))
            return None
        if user.type != ChatType.CHANNEL:
            await event.reply_text(tr("errors.user_not_found"))
            return None
        if effective_chat(event).type != ChatType.SUPERGROUP:
            await event.reply_text(tr("errors.supergroup_only"))
            return None
        if await get_linked_channel(client, effective_chat_id(event), fresh=True) == user.id:
            await event.reply_text(tr("bans.cannot_perform_this_command_on_linked_channels"))
            return None
        name = user.title
    else:
        name = user.first_name
    if not isinstance(user, Chat) and not await can_restrict_member(event, user.id):
        await event.reply_text(tr("permissions.cannot_target_admin"))
        return None
    if mode in {"dban", "dkick"} and not event.reply_to_message_id:
        await event.reply_text(tr("bans.you_have_to_reply_to_a_message"))
        return None
    until = 0
    if mode == "tban":
        until = await extract_time(event, reason)
        if not until:
            await event.reply_text(tr("bans.you_haven_t_specified_a_time_to"))
            return None
    return user.id, name or "User", reason or "", until


async def _ban_command(client, event, mode):
    if not _is_group(event):
        return await event.reply_text(tr("errors.group_only"))
    if not await check_user(event, user_id=sender_id(event), privileges="can_restrict_members"):
        return
    target = await _ban_target(client, event, mode)
    if target is None:
        return
    user_id, name, reason, until = target
    return await execute_operation(
        client,
        event,
        user_id,
        name,
        mode,
        reason,
        until,
        event.id,
        actor_id=sender_id(event),
        actor=actor_name(event),
    )


@command("dban", chat_scope="group")
@anonadmin_checker
async def dban(client, event):
    return await _ban_command(client, event, "dban")


@command("ban", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def ban(client, event):
    return await _ban_command(client, event, "ban")


@command("sban", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def sban(client, event):
    return await _ban_command(client, event, "sban")


@command("dkick", chat_scope="group")
@anonadmin_checker
async def dkick(client, event):
    return await _ban_command(client, event, "dkick")


@command("kick", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def kick(client, event):
    return await _ban_command(client, event, "kick")


@command("unban", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def unban(client, event):
    return await _ban_command(client, event, "unban")


@command("skick", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def skick(client, event):
    return await _ban_command(client, event, "skick")


@command("tban", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
async def tban(client, event):
    return await _ban_command(client, event, "tban")


@command("dnd", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def dnd(client, e):
    user_id = sender_id(e)
    if not await check_user(e, user_id=user_id, privileges="can_change_info"):
        return
    q = e.command[1].lower() if len(e.command) > 1 else None
    x = await xdb.dnd.find_one({"chat_id": effective_chat_id(e)})
    x = x["mode"] if x else False
    if not q:
        if not x:
            await e.reply_text(tr("bans.dnd_mode_is_currently_off_group_is"))
        else:
            await e.reply_text(tr("bans.dnd_mode_is_currently_on_bot_name"))
    elif q in ["on", "yes", "true"]:
        await atomic_upsert(xdb.dnd, {"chat_id": effective_chat_id(e)}, {"$set": {"mode": True}})
        await e.reply_text(tr("bans.dnd_mode_has_been_turned_on"))
        return "DND_ACTIVE", None, None
    elif q in ["off", "no", "false"]:
        await e.reply_text(tr("bans.dnd_mode_has_been_disabled"))
        await atomic_upsert(xdb.dnd, {"chat_id": effective_chat_id(e)}, {"$set": {"mode": False}})
        return "DND_INACTIVE", None, None
    else:
        await e.reply_text(tr("bans.expected_true_false_got", expected_true_false=q))


@listen(filters=pyrofilters.new_chat_members)
async def dndtr(client, message):
    x = await xdb.dnd.find_one({"chat_id": message.chat.id})
    x = x["mode"] if x else None
    if not x:
        return
    for user in message.new_chat_members:
        if not user or user.username or user.is_bot:
            continue
        try:
            if not await can_restrict_member(message, user.id):
                continue
            await client.ban_chat_member(message.chat.id, user.id)
            await client.unban_chat_member(message.chat.id, user.id)
        except (RPCError, RedisError, OSError):
            LOGGER.warning(
                "DND failed to kick user %s in %s", user.id, message.chat.id, exc_info=True
            )
