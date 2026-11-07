from pyrogram.types import Message

from Emilia.utils.saved_message import split_named_arguments


def get_text_reason(message: Message) -> tuple[str, str | None]:
    name, reason = split_named_arguments(message.text)
    return name, reason or None
