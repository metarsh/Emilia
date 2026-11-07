from Emilia.custom_filter import command
from Emilia.database.connection import allow_collection, get_allow_connection
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker

ALLOW_CONNECTION_TRUE = ["on", "yes", "true"]
ALLOW_CONNECTION_FALSE = ["off", "no", "false"]


@command("allowconnection", chat_scope="group_or_channel", allow_connected=True)
@anonadmin_checker
async def allow_connection(client, message):

    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await is_user_admin(message, chat_id=chat_id):
        return

    if len(message.command) >= 2:
        get_arg = message.command[1].lower()

        if get_arg in ALLOW_CONNECTION_TRUE:
            await allow_collection(chat_id, chat_title, allow_collection=True)
            await message.reply(tr("allow_connection.allowed_all_users_in_connection"))
        elif get_arg in ALLOW_CONNECTION_FALSE:
            await allow_collection(chat_id, chat_title, allow_collection=False)
            await message.reply(tr("allow_connection.disallowed_all_users_in_connection"))
        else:
            await message.reply(
                tr("allow_connection.got_need_off_yes_no_true_false", get_arg=get_arg)
            )
    else:
        if await get_allow_connection(chat_id):
            t_message = tr("allow_connection.users_allowed_connect_chat_pm")
        else:
            t_message = tr("allow_connection.users_not_allowed_connect_chat_pm")

        await message.reply(t_message)
