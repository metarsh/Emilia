import asyncio

from pyrogram.enums import ChatType
from pyrogram.errors import RPCError

from Emilia.database.connection import get_allow_connection, get_connection
from Emilia.locales import tr
from Emilia.utils.auth import is_dev
from Emilia.utils.chat_context import bind_target, origin_message
from Emilia.utils.chat_status import get_chat_member_cached, member_is_admin, member_is_present
from Emilia.utils.client_context import bot_id
from Emilia.utils.get_user import normalize_peer
from Emilia.utils.message_actor import actor_id

CONNECTION_TYPES = (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL)


class ConnectionAccessDenied(PermissionError):
    def __init__(self):
        super().__init__(tr("connection.access_denied"))


async def accessible_chat(client, user_id: int, peer):
    if not isinstance(user_id, int) or user_id <= 0:
        return None
    if not isinstance(peer, (int, str)) or not peer:
        return None
    if isinstance(peer, str):
        peer = normalize_peer(peer.strip())
        if not peer:
            return None
    try:
        chat = await asyncio.wait_for(client.get_chat(peer), 10)
    except (TimeoutError, RPCError, ValueError):
        return None
    if chat.type not in CONNECTION_TYPES:
        return None
    bot_member = await get_chat_member_cached(client, chat.id, bot_id(client), fresh=True)
    if not member_is_present(bot_member):
        return None
    if is_dev(user_id):
        return chat
    member = await get_chat_member_cached(client, chat.id, user_id, fresh=True)
    if member_is_admin(member) or (
        member_is_present(member) and await get_allow_connection(chat.id)
    ):
        return chat
    return None


async def connection(event):
    message = origin_message(event)
    if message is None or message.chat.type != ChatType.PRIVATE:
        return None
    if getattr(message, "_emilia_connection_resolved", False):
        return getattr(message, "_emilia_target_chat_id", None)
    user_id = actor_id(event)
    if user_id is None or user_id <= 0:
        return None
    record = await get_connection(user_id)
    if not record or not record.get("connection"):
        message._emilia_connection_resolved = True
        return None
    client = event._client
    chat = await accessible_chat(client, user_id, record.get("connected_chat"))
    if chat is None:
        raise ConnectionAccessDenied()
    bind_target(message, chat)
    message._emilia_connection_resolved = True
    return chat.id
