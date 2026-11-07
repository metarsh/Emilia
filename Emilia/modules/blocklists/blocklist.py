import html

from Emilia.custom_filter import command
from Emilia.database.blocklists import get_blocklist
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker


@command(["blocklist", "blacklist"], chat_scope="group", allow_connected=True)
@anonadmin_checker
async def blocklist(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await is_user_admin(message):
        return

    BLOCKLIST_DATA = await get_blocklist(chat_id)
    if BLOCKLIST_DATA is None or len(BLOCKLIST_DATA) == 0:
        await message.reply(
            tr("blocklist.no_blocklist_filters_active", chat_title=html.escape(chat_title))
        )
        return

    BLOCKLIST_ITMES = []
    for blocklist_array in BLOCKLIST_DATA:
        BLOCKLIST_ITMES.append(blocklist_array["blocklist_text"])

    blocklist_header = tr(
        "blocklist.following_blocklist_filters_currently_active", chat_title=html.escape(chat_title)
    )
    for block_itmes in BLOCKLIST_ITMES:
        blocklist_name = f"• `{block_itmes}`\n"
        blocklist_header += blocklist_name

    await message.reply(blocklist_header)
