from Emilia.custom_filter import command
from Emilia.database.log_channels import unset_log_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker


@command("unsetlog", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def unset_log(client, message):

    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, chat_id=chat_id, privileges="can_change_info"):
        return

    await unset_log_db(chat_id)

    await message.reply(
        tr("unsetlog.successfully_unset_log_channel_admin_actions_will"),
    )
