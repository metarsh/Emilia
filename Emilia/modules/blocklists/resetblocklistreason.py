from Emilia.custom_filter import command
from Emilia.database.blocklists import setblocklistreason_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker


@command("resetblocklistreason", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def resetblocklistreason(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, chat_id=chat_id, privileges="can_change_info"):
        return

    await setblocklistreason_db(chat_id, None)
    await message.reply(tr("resetblocklistreason.the_default_blocklist_reason_has_been_reset"))
