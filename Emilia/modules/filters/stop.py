from Emilia.custom_filter import command
from Emilia.database.filters import get_filters_list, stop_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.saved_message import split_named_arguments


@command("stop", allow_connected=True)
@anonadmin_checker
async def stop(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    try:
        filter_name, _ = split_named_arguments(message.text)
    except ValueError:
        await reply_usage(message, stop)
        return

    if filter_name not in (await get_filters_list(chat_id)):
        await message.reply(tr("stop.you_haven_t_saved_any_filters_on"))
        return

    await stop_db(chat_id, filter_name)
    await message.reply(tr("stop.ve_stopped", filter_name=filter_name))
