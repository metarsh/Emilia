from collections.abc import Iterable

from pyrogram.enums import MessageEntityType

EMOJIPACK_PREFIX = "emojipack:"


def normalize_emojipack_name(name: str) -> str | None:
    if not name:
        return None
    name = str(name).strip()
    if not name:
        return None
    if name.lower().startswith(EMOJIPACK_PREFIX):
        name = name.split(":", 1)[1]
    name = name.strip("<> ")
    return name or None


def emojipack_token(name: str) -> str | None:
    normalized = normalize_emojipack_name(name)
    if normalized is None:
        return None
    return f"{EMOJIPACK_PREFIX}{normalized.lower()}"


def is_emojipack_token(value: str) -> bool:
    return bool(value and str(value).lower().startswith(EMOJIPACK_PREFIX))


def extract_custom_emoji_ids_from_message(message) -> list[int]:
    ids = []
    for attr in ("entities", "caption_entities"):
        for entity in getattr(message, attr, None) or []:
            entity_type = getattr(entity, "type", None)
            if entity_type == MessageEntityType.CUSTOM_EMOJI:
                custom_emoji_id = getattr(entity, "custom_emoji_id", None)
                if custom_emoji_id:
                    try:
                        ids.append(int(custom_emoji_id))
                    except (TypeError, ValueError):
                        pass
    return list(dict.fromkeys(ids))


async def get_pack_names_for_custom_emoji_ids(client, custom_emoji_ids: Iterable[int]) -> set[str]:
    ids = list(dict.fromkeys(int(x) for x in custom_emoji_ids if x))
    if not ids:
        return set()

    pack_names = set()
    for offset in range(0, len(ids), 200):
        stickers = await client.get_custom_emoji_stickers(ids[offset : offset + 200])
        for sticker in stickers:
            token = emojipack_token(sticker.set_name)
            if token:
                pack_names.add(token)
    return pack_names


async def extract_emojipack_tokens(client, message) -> set[str]:
    ids = extract_custom_emoji_ids_from_message(message)
    return await get_pack_names_for_custom_emoji_ids(client, ids)


async def extract_emojipack_tokens_from_command_target(client, message) -> set[str]:
    target = getattr(message, "reply_to_message", None) or message
    return await extract_emojipack_tokens(client, target)
