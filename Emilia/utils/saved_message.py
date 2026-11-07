import re
from enum import Enum

from Emilia.utils.message_content import FormattedText, formatted_text


class SavedMessageType(Enum):
    text = 1
    sticker = 2
    animation = 3
    document = 4
    photo = 5
    audio = 6
    voice = 7
    video = 8
    video_note = 9


def split_named_arguments(text):
    parts = str(text or "").split(None, 1)
    if len(parts) < 2:
        raise ValueError("A name is required")
    arguments = parts[1]
    if arguments.startswith(('"', "'")):
        match = re.match(r"([\"'])(.*?)(?<!\\)\1(?:\s+|$)", arguments, re.S)
        if not match:
            raise ValueError("The quoted name must be closed")
        name = re.sub(r"\\([\"'])", r"\1", match.group(2))
        body = arguments[match.end() :]
    else:
        fields = arguments.split(None, 1)
        name, body = fields[0], fields[1] if len(fields) > 1 else ""
    if not name.strip():
        raise ValueError("A name is required")
    return name, body


def parse_saved_message(message, *, named=True, video_note_text=None):
    reply = message.reply_to_message
    if reply is None:
        raw = message.text or message.caption or ""
        entities = (message.entities if message.text else message.caption_entities) or []
        if named:
            try:
                _, body = split_named_arguments(raw)
            except ValueError:
                return None, "", None
        else:
            fields = raw.split(None, 1)
            body = fields[1] if len(fields) > 1 else ""
        if not body.strip():
            return None, "", None
        document = FormattedText(raw, entities).slice(len(raw) - len(body))
        return None, document.record(), SavedMessageType.text.value
    if reply.text:
        document = FormattedText(reply.text, reply.entities or [])
        return None, document.record(), SavedMessageType.text.value
    for kind in SavedMessageType:
        if kind is SavedMessageType.text:
            continue
        media = getattr(reply, kind.name, None)
        if media is not None:
            text = video_note_text if kind is SavedMessageType.video_note else reply.caption or ""
            document = FormattedText(text or "", reply.caption_entities or [])
            return media.file_id, document.record(), kind.value
    return None, "", None


def rules_markup(client, chat_id):
    from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    from Emilia.locales import tr
    from Emilia.utils.client_context import bot_username

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("filters.rules"),
                    url=f"https://t.me/{bot_username(client)}?start=rules_{chat_id}",
                )
            ]
        ]
    )


async def send_saved_message(
    client,
    chat_id,
    content,
    text,
    data_type,
    *,
    reply_markup=None,
    reply_message_id=None,
    preview_disabled=True,
):
    from pyrogram.enums import ParseMode
    from pyrogram.types import LinkPreviewOptions, ReplyParameters

    native = formatted_text(text)
    kind = SavedMessageType(data_type)
    options = {"chat_id": chat_id, "reply_markup": reply_markup}
    if reply_message_id is not None:
        options["reply_parameters"] = ReplyParameters(message_id=reply_message_id)
    if kind is SavedMessageType.text:
        return await client.send_message(
            text=native.text,
            entities=native.entities,
            parse_mode=ParseMode.DISABLED,
            link_preview_options=LinkPreviewOptions(is_disabled=preview_disabled),
            **options,
        )
    options[kind.name] = content
    if kind not in (SavedMessageType.sticker, SavedMessageType.video_note):
        options["caption"] = native.text
        options["caption_entities"] = native.entities
        options["parse_mode"] = ParseMode.DISABLED
    return await getattr(client, f"send_{kind.name}")(**options)
