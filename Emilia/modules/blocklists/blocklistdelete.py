from Emilia.custom_filter import command
from Emilia.database.blocklists import (
    blocklistMessageDelete,
    getblocklistMessageDelete,
)
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import bot_has_permission, user_has_permission
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker

BLOCKLIST_DELETE_TRUE = ["on", "yes"]
BLOCKLIST_DELETE_FALSE = ["off", "no"]


@command("blocklistdelete", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def blocklistdelete(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, chat_id=chat_id, privileges="can_change_info"):
        return

    if not await bot_has_permission(message, chat_id=chat_id, privileges="can_delete_messages"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]

        if args in BLOCKLIST_DELETE_TRUE:
            await blocklistMessageDelete(chat_id, True)
            await message.reply(tr("blocklistdelete.blocklist_deletes_have_now_been_enabled_i"))

        elif args in BLOCKLIST_DELETE_FALSE:
            await blocklistMessageDelete(chat_id, False)
            await message.reply(tr("blocklistdelete.blocklist_deletes_have_now_been_disabled_i"))

        else:
            await reply_usage(message, blocklistdelete)
    else:
        if getblocklistMessageDelete:
            await message.reply(
                tr("blocklistdelete.i_am_currently_deleting_all_blocklisted_messages")
            )
        else:
            await message.reply(
                tr("blocklistdelete.i_am_currently_not_deleting_blocklisted_messages")
            )
