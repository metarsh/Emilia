from Emilia.custom_filter import command
from Emilia.database.disable import disabledel_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_bot, check_user
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker

DISABLEDEL_TRUE = ["on", "yes"]
DISABLEDEL_FALSE = ["off", "no"]


@command("disabledel", chat_scope="group_or_channel", allow_connected=True)
@anonadmin_checker
async def disabledel(client, message):
    chat_id = effective_chat_id(message)

    if not await check_bot(message, privileges="can_delete_messages", chat_id=chat_id):
        return

    if not await check_user(message, privileges="can_change_info", chat_id=chat_id):
        return

    if len(message.command) >= 2:
        arg = message.command[1].lower()
        if arg in DISABLEDEL_TRUE:
            await disabledel_db(chat_id, True)
            await message.reply(tr("disabledel.disabled_messages_will_now_be_deleted"))

        elif arg in DISABLEDEL_FALSE:
            await disabledel_db(chat_id, False)
            await message.reply(tr("disabledel.disabled_messages_will_no_longer_be_deleted"))

        else:
            await message.reply(tr("errors.invalid_toggle"))
    else:
        await reply_usage(message, disabledel)
        return
