from pymongo.errors import PyMongoError
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardMarkup, Message
from redis.exceptions import RedisError

from Emilia.application import LOGGER
from Emilia.database.notes import GetNote
from Emilia.locales import tr
from Emilia.utils.button_gen import button_markdown_parser
from Emilia.utils.chat_context import (
    bind_target,
    connected_chat_id,
    effective_chat_id,
    reset_context,
    restore_context,
)
from Emilia.utils.errors import telegram_error_text
from Emilia.utils.message_content import prefix_content, replace_content, text_value
from Emilia.utils.note_format import NoteFillings
from Emilia.utils.note_permissions import (
    preview_text_replace,
    privateNote_and_admin_checker,
    strip_note_tags,
)
from Emilia.utils.saved_message import rules_markup, send_saved_message


async def SendNoteMessage(client, message: Message, note_name: str, from_chat_id: int):
    connected = connected_chat_id(message)
    source_chat_id = effective_chat_id(message)
    if from_chat_id is not None:
        source_chat_id = from_chat_id
    private = connected is not None or from_chat_id is not None
    chat_id = message.from_user.id if private else message.chat.id
    reply_id = (
        message.id if private or not message.reply_to_message else message.reply_to_message.id
    )
    content, text, data_type = await GetNote(source_chat_id, note_name)
    _, allow = await privateNote_and_admin_checker(message, text, chat_id=source_chat_id)
    if not allow:
        return
    text = strip_note_tags(text)
    if from_chat_id is not None and connected is None:
        text = prefix_content(text, f"{note_name}:\n\n")
    text, buttons = button_markdown_parser(text)
    preview, text = preview_text_replace(text)
    text = NoteFillings(message, text)
    markup = InlineKeyboardMarkup(buttons) if buttons else None
    if not buttons and "{rules}" in text_value(text):
        text = replace_content(text, "{rules}", "")
        markup = rules_markup(client, source_chat_id)
    text = text if text_value(text).strip() else note_name
    return await send_saved_message(
        client,
        chat_id,
        content,
        text,
        data_type,
        reply_markup=markup,
        reply_message_id=reply_id,
        preview_disabled=preview,
    )


async def exceNoteMessageSender(client, message, note_name, from_chat_id=None):
    previous = reset_context(message) if from_chat_id is not None else None
    try:
        if from_chat_id is not None:
            bind_target(message, await client.get_chat(from_chat_id))
        return await SendNoteMessage(client, message, note_name, from_chat_id)
    except (RPCError, PyMongoError, RedisError, OSError) as exc:
        LOGGER.exception("Note delivery failed for chat %s", message.chat.id)
        await message.reply(telegram_error_text(exc) or tr("notes.delivery_failed"))
    finally:
        if previous is not None:
            restore_context(message, previous)
