import html

from pyrogram.enums import ParseMode
from pyrogram.errors import BadRequest

from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import bot_has_permission, can_restrict_member, check_admins
from Emilia.utils.client_context import bot_id
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.get_user import get_text, get_user_id, mention_html
from Emilia.utils.message_actor import actor_id, actor_name
from Emilia.utils.restrictions import restrict_member


@command(["mute", "smute"], chat_scope="supergroup", allow_connected=True)
async def mute(client, message):
    return await _mute(client, message)


@command("dmute", chat_scope="supergroup", require_reply=True)
async def dmute(client, message):
    return await _mute(client, message)


@anonadmin_checker
@log_to_channel
async def _mute(client, message):
    chat_id = effective_chat_id(message)
    message_id = None
    mode = message.command[0]
    if not await check_admins(message, privileges="can_restrict_members"):
        return

    user_info = await get_user_id(message)
    if user_info is None:
        return
    user_id = user_info.id

    if user_id == bot_id(client):
        await message.reply(tr("mute.yup_let_me_just_ban_myself_yay"))
        return

    if mode == "dmute" and not await bot_has_permission(message, privileges="can_delete_messages"):
        return

    if not await can_restrict_member(message, user_id):
        await message.reply(tr("mute.surely_i_don_t_plan_to_mute"))
        return

    try:
        await restrict_member(chat_id, user_id, client=client)
    except BadRequest:
        return await message.reply(tr("mute.give_me_ban_user_rights_to_perform"))

    if mode == "dmute":
        if message.reply_to_message:
            message_id = message.reply_to_message.id

    elif mode == "smute":
        message_id = message.id

    if mode != "smute":
        actor_html = mention_html(actor_id(message), actor_name(message), client=client)
        target_html = mention_html(user_info.id, user_info.first_name, client=client)
        text = tr("mute.yep_has_muted", target_html=target_html, actor_html=actor_html)

        reason = get_text(message)
        if reason:
            text += tr("bans.execute_operation_reason", reason=html.escape(reason))

        await message.reply(text, parse_mode=ParseMode.HTML)

    # Deletaion of message according to user admin command
    if message_id is not None:
        await client.delete_messages(chat_id=message.chat.id, message_ids=message_id)

    return "MUTE", user_info.id, user_info.first_name
