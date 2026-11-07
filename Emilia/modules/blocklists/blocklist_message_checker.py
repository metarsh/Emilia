import re
import unicodedata
from functools import lru_cache

from pyrogram import Client, filters
from redis.exceptions import RedisError

from Emilia.application import LOGGER
from Emilia.database.approval import is_approved
from Emilia.database.blocklists import get_blocklist
from Emilia.modules.blocklists.checker import blocklist_action
from Emilia.utils.allowlist import extract_message_urls
from Emilia.utils.chat_status import is_bot_admin, is_user_admin
from Emilia.utils.custom_emoji import extract_emojipack_tokens, is_emojipack_token
from Emilia.utils.message_actor import actor_id, sender_entity


def _normalize(text: str) -> str:
    """Normalize compatibility characters and remove Unicode format characters."""
    text = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


@lru_cache(maxsize=512)
def _get_compiled_patterns(items: tuple[str, ...]):
    return tuple(
        (
            word,
            re.compile(r"(?<!\w)" + re.escape(_normalize(word)) + r"(?!\w)", re.IGNORECASE),
        )
        for word in items
        if "*" not in word and not is_emojipack_token(word)
    )


@Client.on_message(filters.all & filters.group, group=3)
async def blocklist_checker(client, message):
    if sender_entity(message) is None:
        return
    chat_id = message.chat.id

    try:
        if not await is_bot_admin(message, silent=True):
            return
        if await is_user_admin(message, silent=True):
            return
    except RedisError as exc:
        LOGGER.warning(f"blocklist_checker admin-check failed in {chat_id}: {exc}")
        return

    user_id = actor_id(message)

    if await is_approved(chat_id, user_id):
        return

    blocklist_data = await get_blocklist(chat_id)
    if not blocklist_data:
        return

    blocklist_items = [b["blocklist_text"] for b in blocklist_data]

    message_text = extract_text(message)
    emojipack_blocklists = {item.lower() for item in blocklist_items if is_emojipack_token(item)}
    if emojipack_blocklists:
        message_packs = await extract_emojipack_tokens(client, message)
        for pack in message_packs:
            if pack in emojipack_blocklists:
                await blocklist_action(client, message, pack)
                return

    for item in blocklist_items:
        if is_emojipack_token(item) or "*" not in item:
            continue
        star_position = item.index("*")
        if star_position > 0 and item[star_position - 1] == "/":
            block_char = item[:star_position]
            urls = extract_message_urls(message)
            for url in urls:
                if block_char in url:
                    await blocklist_action(client, message, f"{block_char}*")
                    return

        elif star_position + 1 < len(item) and item[star_position + 1] == ".":
            if message.document or message.animation:
                extensions = item[star_position + 1 :]
                file_name = None
                if message.document:
                    file_name = message.document.file_name
                elif message.animation:
                    file_name = message.animation.file_name
                if file_name and file_name.endswith(extensions):
                    await blocklist_action(client, message, f"*{extensions}")
                    return

    if message_text:
        normalized_text = _normalize(message_text)
        for word, pattern in _get_compiled_patterns(tuple(blocklist_items)):
            if pattern.search(normalized_text):
                await blocklist_action(client, message, word)
                return


def extract_text(message) -> str:
    return message.text or message.caption or (message.sticker.emoji if message.sticker else None)
