import html
from datetime import datetime

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import BadRequest
from pyrogram.types import Chat, Message

from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import (
    can_restrict_member,
    check_admins,
)
from Emilia.utils.client_context import bot_id
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import (
    anonadmin_checker,
    log_to_channel,
)
from Emilia.utils.get_user import mention_html, resolve_target
from Emilia.utils.message_actor import actor_id, actor_name
from Emilia.utils.restrictions import restrict_member
from Emilia.utils.time import time_converter


@command(["tmute", "tempmute"], chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def mute(client: Client, message: Message):
    if not await check_admins(message, privileges="can_restrict_members"):
        return

    target_user, remainder = await resolve_target(message, allow_chats=True)
    if target_user is None:
        return await message.reply(tr("errors.user_not_found"))
    parts = (remainder or "").split(None, 1)
    time_val = parts[0] if parts else None
    reason = parts[1] if len(parts) > 1 else None

    if isinstance(target_user, Chat) or getattr(target_user, "first_name", None) is None:
        await message.reply(tr("tmute.cannot_perform_this_command_on_anonymous_admins"))
        return

    if target_user.id == bot_id(client):
        await message.reply(tr("mute.yup_let_me_just_ban_myself_yay"))
        return

    if not await can_restrict_member(message, target_user.id):
        await message.reply(tr("mute.surely_i_don_t_plan_to_mute"))
        return

    if not time_val:
        await reply_usage(message)
        return

    temp_mute = await time_converter(message, time_val)
    if not temp_mute or not isinstance(temp_mute, datetime):
        return

    actor_html = mention_html(actor_id(message), actor_name(message), client=client)
    target_first_name = target_user.first_name or "User"
    target_html = target_user.mention(style=ParseMode.HTML)

    msg = tr(
        "tmute.yep_has_temporarily_muted",
        target_html=target_html,
        time_val=time_val,
        actor_html=actor_html,
    )
    if reason:
        msg += tr("bans.execute_operation_reason", reason=html.escape(reason))

    until_ts = int(temp_mute.timestamp()) if hasattr(temp_mute, "timestamp") else int(temp_mute)

    try:
        await restrict_member(
            effective_chat_id(message), target_user.id, until_date=until_ts, client=client
        )
        await message.reply_text(msg, parse_mode=ParseMode.HTML)
    except BadRequest:
        await message.reply(tr("tmute.give_me_ban_user_rights_to_perform"))
        return

    return "TEMP_MUTE", target_user.id, target_first_name
