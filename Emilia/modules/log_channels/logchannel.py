import html

from Emilia.custom_filter import command
from Emilia.database.log_channels import get_set_channel
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker


@command("logchannel", allow_connected=True, chat_scope="group")
@anonadmin_checker
async def logcategories(client, message):

    chat_id = effective_chat_id(message)

    if not await is_user_admin(message, chat_id=chat_id):
        return

    if await get_set_channel(chat_id) is not None:
        channel_title = await get_set_channel(chat_id)
        await message.reply(
            tr(
                "logchannel.i_am_currently_logging_admin_actions_in",
                channel_title=html.escape(channel_title),
            ),
        )
    else:
        await message.reply(tr("logchannel.there_are_no_log_channels_assigned_to"))
