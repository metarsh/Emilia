from Emilia.custom_filter import command
from Emilia.modules.warnings.warn import warn
from Emilia.utils.chat_status import bot_has_permission, user_has_permission
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.get_user import get_text


@command(["warn", "swarn"], chat_scope="group", allow_connected=True)
async def addwarn(client, message):
    return await _addwarn(client, message)


@command("dwarn", chat_scope="group", require_reply=True)
async def dwarn(client, message):
    return await _addwarn(client, message)


@anonadmin_checker
@log_to_channel
async def _addwarn(client, message):
    chat_id = message.chat.id
    message_id = None
    silent = False

    if not await user_has_permission(message, privileges="can_restrict_members"):
        return

    if not await bot_has_permission(message, privileges="can_restrict_members"):
        return

    mode = message.command[0]
    if mode == "dwarn" and not await bot_has_permission(message, privileges="can_delete_messages"):
        return

    reason = get_text(message)
    if not reason:
        reason = None

    if mode == "dwarn":
        if message.reply_to_message:
            message_id = message.reply_to_message.id

    elif mode == "swarn":
        message_id = message.id
        silent = True

    warn_r, log_msg, info = await warn(client, message, reason, silent, warn_user=None)

    if warn_r:
        if message_id is not None:
            await client.delete_messages(chat_id=chat_id, message_ids=message_id)
    if info is not None:
        return log_msg, info.id, info.first_name
