from urllib.parse import urlsplit

from pyrogram.enums import MessageEntityType
from urlextract import URLExtract

_URL_EXTRACTOR = URLExtract()


def extract_message_urls(message) -> list[str]:
    urls = _URL_EXTRACTOR.find_urls(message.text or message.caption or "")
    urls.extend(
        entity.url
        for entity in (*(message.entities or []), *(message.caption_entities or []))
        if entity.type == MessageEntityType.TEXT_LINK and entity.url
    )
    return list(dict.fromkeys(urls))


def is_telegram_invite_url(value: str) -> bool:
    try:
        parsed = urlsplit(value if "://" in value else f"//{value}")
    except ValueError:
        return False
    return parsed.hostname in {"t.me", "telegram.me", "telegram.dog"} and (
        parsed.path.startswith("/joinchat/") or parsed.path.startswith("/+")
    )


def sender_is_allowlisted(sender, entries) -> bool:
    if sender is None:
        return False
    return sender.id in entries or bool(
        sender.username
        and any(
            isinstance(item, str) and item.lower() == f"@{sender.username.lower()}"
            for item in entries
        )
    )


def normalize_allowlist_url(value: str) -> str:
    parsed = urlsplit(value if "://" in value else f"//{value}")
    host = parsed.netloc.lower().removeprefix("www.")
    result = host + parsed.path
    if parsed.query:
        result += "?" + parsed.query
    if parsed.fragment:
        result += "#" + parsed.fragment
    return result
