from Emilia.custom_filter import command
from Emilia.database.welcome import SetGoodBye
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.welcome_content import GetWelcomeMessage


@command("setgoodbye", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def set_goodbye(client, message):
    ChatID = effective_chat_id(message)

    if not await user_has_permission(message, privileges="can_change_info"):
        return

    command = message.text.split(" ")
    if not message.reply_to_message and len(command) == 1:
        return await message.reply(tr("set_goodbye.you_need_to_give_the_goodbye_message"))

    CONTENT, TEXT, DATATYPE = GetWelcomeMessage(message)
    await SetGoodBye(ChatID, CONTENT, TEXT, DATATYPE)
    await message.reply(tr("set_goodbye.the_new_goodbye_message_has_been_saved"))
