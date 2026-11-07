import html
import re

from pyrogram.enums import MessageEntityType
from pyrogram.types import MessageEntity

from Emilia.utils.chat_context import effective_chat
from Emilia.utils.get_user import mention_html
from Emilia.utils.message_actor import actor_user
from Emilia.utils.message_content import formatted_text, replace_range, text_value, utf16_length

CONTEXT_FIELD = re.compile(r"\{(id|first|last|fullname|username|mention|chatname|count)\}")


def _escape_context(value):
    text = html.escape(str(value or ""))
    # Decode these characters only after the Markdown parser has read delimiters.
    for character in "*_~|`[]":
        text = text.replace(character, f"&#{ord(character)};")
    return text


def context_fields(user, chat_title):
    first = _escape_context(user.first_name)
    last = _escape_context(user.last_name)
    fullname = " ".join(part for part in (first, last) if part)
    mention = mention_html(
        user.id,
        " ".join(part for part in (user.first_name, user.last_name) if part),
        client=user._client,
    )
    return {
        "id": str(user.id),
        "first": first,
        "last": last,
        "fullname": fullname,
        "username": _escape_context(user.username) if user.username else mention,
        "mention": mention,
        "chatname": _escape_context(chat_title),
    }


def fill_context_fields(text, values):
    return CONTEXT_FIELD.sub(lambda match: values.get(match[1], match[0]), text)


def fill_native_context(value, user, chat_title, *, count=None):
    value = formatted_text(value)
    fullname = " ".join(part for part in (user.first_name, user.last_name) if part)
    values = {
        "id": str(user.id),
        "first": user.first_name or "",
        "last": user.last_name or "",
        "fullname": fullname,
        "username": "@" + user.username if user.username else fullname,
        "mention": fullname,
        "chatname": chat_title or "",
        "count": str(count) if count is not None else "",
    }
    matches = list(CONTEXT_FIELD.finditer(text_value(value)))
    for match in reversed(matches):
        key = match[1]
        replacement = values[key]
        entities = []
        if key == "mention" or (key == "username" and not user.username):
            entities.append(
                MessageEntity(
                    type=MessageEntityType.TEXT_MENTION,
                    offset=0,
                    length=utf16_length(replacement),
                    user=user,
                )
            )
        value = replace_range(value, match.start(), match.end(), replacement, entities)
    return value


def NoteFillings(message, message_text):
    if message is None or actor_user(message) is None:
        return message_text
    return fill_native_context(message_text, actor_user(message), effective_chat(message).title)
