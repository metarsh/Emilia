from pyrogram.types import CallbackQuery, Chat, Message


def origin_message(event: Message | CallbackQuery) -> Message | None:
    return event.message if isinstance(event, CallbackQuery) else event


def effective_chat(event: Message | CallbackQuery) -> Chat | None:
    message = origin_message(event)
    if message is None:
        return None
    return getattr(message, "_emilia_target_chat", None) or message.chat


def effective_chat_id(event: Message | CallbackQuery) -> int | None:
    message = origin_message(event)
    chat = effective_chat(event)
    return getattr(message, "_emilia_target_chat_id", None) or (chat.id if chat else None)


def connected_chat_id(event):
    message = origin_message(event)
    if message is None or not getattr(message, "_emilia_connection_resolved", False):
        return None
    return getattr(message, "_emilia_target_chat_id", None)


def bind_target(message: Message, chat: Chat) -> None:
    message._emilia_target_chat = chat
    message._emilia_target_chat_id = chat.id


CONTEXT_ATTRIBUTES = (
    "_emilia_target_chat",
    "_emilia_target_chat_id",
    "_emilia_connection_resolved",
    "_emilia_anonymous_admin_allowed",
)

_MISSING = object()


def reset_context(message):
    previous = {}
    if message is not None:
        for attribute in CONTEXT_ATTRIBUTES:
            previous[attribute] = getattr(message, attribute, _MISSING)
            if hasattr(message, attribute):
                delattr(message, attribute)
    return previous


def restore_context(message, previous):
    for attribute, value in previous.items():
        if value is _MISSING:
            if hasattr(message, attribute):
                delattr(message, attribute)
        else:
            setattr(message, attribute, value)
