from Emilia.custom_filter import command
from Emilia.database.disable import get_disabled
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker


@command("disabled", chat_scope="group_or_channel", allow_connected=True)
@anonadmin_checker
async def disable(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    DISABLE_LIST = await get_disabled(chat_id)

    if len(DISABLE_LIST) == 0:
        await message.reply(tr("disabled.there_are_no_disabled_commands_in_this"))
        return

    text = tr("disabled.following_commands_disabled_chat")
    for item in DISABLE_LIST:
        text += f"- `{item}`\n"

    await message.reply(text)
