import html

from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.message_links import message_reference


@command("pinned")
async def pinned(client, message):
    chat_id = message.chat.id
    chat_title = message.chat.title

    chat_data = await client.get_chat(chat_id=chat_id)
    if chat_data.pinned_message:
        reference = message_reference(chat_data.pinned_message, "here")
        await message.reply(
            tr(
                "pinned.pinned_message_here",
                chat_title=html.escape(chat_title),
                message_reference=reference,
            )
        )

    else:
        await message.reply(
            tr("pinned.there_no_pinned_message", chat_title=html.escape(chat_title))
        )
