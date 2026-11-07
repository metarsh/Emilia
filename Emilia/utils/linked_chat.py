from pyrogram.enums import ChatType

from Emilia.utils.cache import linked_chat_cache
from Emilia.utils.client_context import bot_id


async def get_linked_channel(client, chat_id: int, *, fresh=False):
    cache_key = f"{bot_id(client)}:{chat_id}"
    if not fresh:
        cached = await linked_chat_cache.get(cache_key)
        if cached is not None:
            return cached["id"]
    chat = await client.get_chat(chat_id)
    linked_id = (
        chat.linked_chat.id
        if chat.type == ChatType.SUPERGROUP
        and chat.linked_chat
        and chat.linked_chat.type == ChatType.CHANNEL
        else None
    )
    await linked_chat_cache.set(cache_key, {"id": linked_id})
    return linked_id


async def is_linked_forward(client, message) -> bool:
    if not message or not message.automatic_forward or not message.sender_chat:
        return False
    if message.chat.type != ChatType.SUPERGROUP or message.sender_chat.type != ChatType.CHANNEL:
        return False
    return message.sender_chat.id == await get_linked_channel(client, message.chat.id, fresh=True)
