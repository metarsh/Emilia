from Emilia.custom_filter import command
from Emilia.database.blocklists import getblocklistmode, setblocklistreason_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker


@command("setblocklistreason", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def setblocklistreason(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, chat_id=chat_id, privileges="can_change_info"):
        return

    blocklist_mode, blocklist_time, blocklist_default_reason = await getblocklistmode(chat_id)

    parts = message.text.markdown.split(None, 1)
    if len(parts) >= 2:
        set_reason = parts[1]
        await setblocklistreason_db(chat_id, set_reason)
        await message.reply(
            tr(
                "setblocklistreason.the_default_blocklist_reason_has_been_set",
                set_reason=set_reason,
            )
        )
    else:
        if blocklist_default_reason is None:
            await message.reply(tr("setblocklistreason.no_default_blocklist_message_has_been_set"))
        else:
            await message.reply(
                tr(
                    "setblocklistreason.current_blocklist_reason",
                    blocklist_default_reason=blocklist_default_reason,
                )
            )
