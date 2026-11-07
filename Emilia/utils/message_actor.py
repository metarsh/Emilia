import html

from pyrogram.enums import ChatType
from pyrogram.types import CallbackQuery


def sender_entity(message):
    return getattr(message, "sender_chat", None) or getattr(message, "from_user", None)


def is_anonymous_admin(message) -> bool:
    chat = getattr(message, "chat", None)
    sender = getattr(message, "sender_chat", None)
    return bool(
        chat
        and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
        and sender
        and sender.id == chat.id
        and sender.type in (ChatType.GROUP, ChatType.SUPERGROUP)
    )


def actor_user(message):
    verified = getattr(message, "_emilia_verified_user", None) or getattr(
        message, "_emilia_bot2bot_reviewer", None
    )
    if verified is not None:
        return verified
    return None if getattr(message, "sender_chat", None) else getattr(message, "from_user", None)


def actor_id(event) -> int | None:
    if isinstance(event, CallbackQuery):
        return event.from_user.id if event.from_user else None
    verified = getattr(event, "_emilia_verified_user_id", None) or getattr(
        event, "_emilia_bot2bot_reviewer_id", None
    )
    user = actor_user(event)
    sender = getattr(event, "sender_chat", None)
    return verified or (user.id if user else sender.id if sender else None)


def actor_name(message) -> str:
    user = actor_user(message)
    if user is not None:
        return user.first_name or "User"
    sender = getattr(message, "sender_chat", None)
    return (sender.title if sender else None) or "User"


def message_actor(message) -> tuple[int | None, str]:
    user = actor_user(message)
    if user is not None:
        return user.id, user.mention

    sender_chat = getattr(message, "sender_chat", None)
    if sender_chat is not None:
        title = html.escape(str(getattr(sender_chat, "title", None) or "User"), quote=False)
        return sender_chat.id, title.replace("\r", " ").replace("\n", " ")

    return None, "User"
