from Emilia.custom_filter import command
from Emilia.database.users import add_chat
from Emilia.locales import tr
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker


@command("forcecachechat", chat_scope="group")
@anonadmin_checker
async def forcecachechat(client, message):
    chat_id = message.chat.id
    chat_title = message.chat.title

    if not await is_user_admin(message):
        return

    await add_chat(chat_id, chat_title)
    await message.reply(tr("forcecachechat.i_ve_exported_your_chat_s_data"))
