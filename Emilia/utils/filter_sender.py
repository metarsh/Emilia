from pyrogram.types import InlineKeyboardMarkup, Message

from Emilia.utils.button_gen import button_markdown_parser
from Emilia.utils.decorators import rate_limit
from Emilia.utils.message_content import replace_content, text_value
from Emilia.utils.note_format import NoteFillings
from Emilia.utils.note_permissions import preview_text_replace
from Emilia.utils.saved_message import rules_markup, send_saved_message
from Emilia.utils.tg_safe import flood_safe


@rate_limit((10, 5))
async def SendFilterMessage(
    client,
    message: Message,
    content: str,
    text: str,
    data_type: int,
    reply_to_sender: bool = False,
):
    reply_id = (
        message.reply_to_message.id if reply_to_sender and message.reply_to_message else message.id
    )
    text, buttons = button_markdown_parser(text)
    text = NoteFillings(message, text)
    preview, text = preview_text_replace(text)
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    if not buttons and "{rules}" in text_value(text):
        text = replace_content(text, "{rules}", "")
        markup = rules_markup(client, message.chat.id)
    return await flood_safe(
        lambda: send_saved_message(
            client,
            message.chat.id,
            content,
            text,
            data_type,
            reply_markup=markup,
            reply_message_id=reply_id,
            preview_disabled=preview,
        ),
        retries=2,
    )
