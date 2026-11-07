from Emilia.custom_filter import command
from Emilia.database.welcome import UnSetGoodbye
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker


@command("resetgoodbye", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def ResetGoodbye(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, privileges="can_change_info"):
        return
    await UnSetGoodbye(chat_id)
    await message.reply(tr("reset_goodbye.the_goodbye_message_has_been_reset_to"))
