from Emilia.custom_filter import command
from Emilia.database.welcome import SetWelcome
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.welcome_content import GetWelcomeMessage


@command("setwelcome", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def set_welcome(client, message):
    ChatID = effective_chat_id(message)

    if not await user_has_permission(message, chat_id=ChatID, privileges="can_change_info"):
        return

    if not message.reply_to_message or len(message.text.split()) > 1:
        return await message.reply(tr("set_welcome.you_need_to_give_the_welcome_message"))

    CONTENT, TEXT, DATATYPE = GetWelcomeMessage(message)
    await SetWelcome(ChatID, CONTENT, TEXT, DATATYPE)
    await message.reply(tr("set_welcome.the_new_welcome_message_has_been_saved"))
