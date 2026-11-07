import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from pyrogram import raw
from pyrogram.enums import MessageEntityType, ParseMode
from pyrogram.errors import BadRequest
from pyrogram.types import Chat, Message, User

from Emilia.utils.command_help import reply_usage
from Emilia.utils.message_actor import sender_entity
from Emilia.utils.message_content import utf16_length
from Emilia.utils.tg_safe import flood_safe


def normalize_peer(value: str) -> int | str:
    return int(value) if re.fullmatch(r"[+-]?\d+", value) else value


def utf16_slice(text: str, offset: int, length: int | None = None) -> str:
    encoded = text.encode("utf-16-le")
    end = None if length is None else (offset + length) * 2
    return encoded[offset * 2 : end].decode("utf-16-le")


def _link_target(url: str | None) -> int | str | None:
    if not url:
        return None
    if url.startswith(("t.me/", "telegram.me/")):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme == "tg" and parsed.netloc == "user":
        value = parse_qs(parsed.query).get("id", [""])[0]
        return int(value) if value.isdecimal() else None
    if parsed.netloc.lower() in ("t.me", "telegram.me"):
        username = parsed.path.strip("/")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,31}", username):
            return "@" + username
    return None


@dataclass(frozen=True)
class TargetArguments:
    target: User | Chat | int | str | None
    remainder: str | None
    explicit: bool = False


def reply_target(message: Message, *, default_to_sender: bool = False) -> User | Chat | None:
    source = message.reply_to_message
    if source is None and default_to_sender:
        source = message
    return sender_entity(source) if source is not None else None


def target_arguments(message: Message) -> TargetArguments:
    text = message.text or message.caption or ""
    match = re.match(r"\s*\S+\s+", text)
    start = match.end() if match else len(text)
    arguments = text[start:]
    token = arguments.split(None, 1)[0] if arguments else ""
    offset = utf16_length(text[:start])
    entities = (message.entities if message.text else message.caption_entities) or []
    for entity in entities:
        if entity.offset != offset:
            continue
        target = None
        if entity.type == MessageEntityType.TEXT_MENTION:
            target = entity.user
        elif entity.type == MessageEntityType.MENTION:
            target = utf16_slice(text, entity.offset, entity.length)
        elif entity.type in (MessageEntityType.TEXT_LINK, MessageEntityType.URL):
            target = _link_target(
                entity.url
                if entity.type == MessageEntityType.TEXT_LINK
                else utf16_slice(text, entity.offset, entity.length)
            )
        if target is not None:
            remainder = utf16_slice(text, entity.offset + entity.length).strip() or None
            return TargetArguments(target, remainder, True)
    target = normalize_peer(token) if token else None
    if token and (isinstance(target, int) or token.startswith("@") or _link_target(token)):
        rest = arguments[len(token) :].strip() or None
        return TargetArguments(_link_target(token) or target, rest, True)
    reply = message.reply_to_message
    if reply is not None:
        return TargetArguments(reply_target(message), arguments.strip() or None)
    return (
        TargetArguments(normalize_peer(token), None, True) if token else TargetArguments(None, None)
    )


async def resolve_peer_target(
    client, target: User | Chat | int | str | None, *, allow_chats: bool = False
) -> User | Chat | None:
    if isinstance(target, Chat):
        return target if allow_chats else None
    if isinstance(target, User) or target is None:
        return target
    if isinstance(target, str):
        target = target.strip()
        target = _link_target(target) or normalize_peer(target)
    try:
        if isinstance(target, int) and target < 0:
            resolved = await flood_safe(lambda: client.get_chat(target)) if allow_chats else None
        elif allow_chats and isinstance(target, str):
            peer = await flood_safe(lambda: client.resolve_peer(target))
            if isinstance(peer, (raw.types.InputPeerChat, raw.types.InputPeerChannel)):
                resolved = await flood_safe(lambda: client.get_chat(target))
            else:
                resolved = await flood_safe(lambda: client.get_users(target))
        else:
            resolved = await flood_safe(lambda: client.get_users(target))
    except BadRequest:
        return None
    return resolved


async def resolve_target(
    message: Message, *, allow_chats: bool = False, default_to_sender: bool = False
) -> tuple[User | Chat | None, str | None]:
    parsed = target_arguments(message)
    target = parsed.target
    if default_to_sender and not parsed.explicit and message.reply_to_message is None:
        target = reply_target(message, default_to_sender=True)
    resolved = await resolve_peer_target(message._client, target, allow_chats=allow_chats)
    return resolved, parsed.remainder


async def get_user_id(message):
    user, _ = await resolve_target(message)
    if user is None:
        await reply_usage(message)
    return user


def get_text(message):
    return target_arguments(message).remainder


def mention_html(peer_id: int | None, name: str, *, client) -> str:
    if peer_id is None or peer_id <= 0:
        from html import escape

        return escape(name)
    return User(client=client, id=peer_id, first_name=name).mention(style=ParseMode.HTML)
