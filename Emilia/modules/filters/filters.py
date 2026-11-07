import html

from Emilia.custom_filter import command
from Emilia.database.filters import get_filters_list
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id


@command("filters", allow_connected=True)
async def filters(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title or "local"
    FILTERS = await get_filters_list(chat_id)

    if len(FILTERS) == 0:
        await message.reply(tr("filters.no_filters", chat_title=html.escape(chat_title)))
        return

    filters_list = tr("filters.list_filters", chat_title=html.escape(chat_title))

    for filter_ in FILTERS:
        filters_list += f"• `{filter_}`\n"

    await message.reply(filters_list)
