from pyrogram.types import InlineKeyboardMarkup

from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.message_content import replace_content, text_value
from Emilia.utils.note_permissions import preview_text_replace
from Emilia.utils.saved_message import rules_markup, send_saved_message
from Emilia.utils.welcome_format import Welcomefillings


async def SendWelcomeMessage(client, message, NewUserJson, content, text, data_type, reply_markup):
    text = await Welcomefillings(message, text, NewUserJson)
    preview, text = preview_text_replace(text)
    if "{rules}" in text_value(text):
        text = replace_content(text, "{rules}", "")
        rows = reply_markup.inline_keyboard if reply_markup else []
        reply_markup = InlineKeyboardMarkup(
            rows + rules_markup(client, effective_chat_id(message)).inline_keyboard
        )
    return await send_saved_message(
        client,
        message.chat.id,
        content,
        text,
        data_type,
        reply_markup=reply_markup,
        preview_disabled=preview,
    )
