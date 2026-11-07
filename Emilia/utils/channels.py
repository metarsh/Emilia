from pyrogram.enums import ChatType

from Emilia.locales import tr
from Emilia.utils.chat_status import (
    get_chat_member_cached,
    has_chat_permission,
    member_has_permission,
    member_is_present,
)
from Emilia.utils.client_context import bot_id
from Emilia.utils.get_user import normalize_peer
from Emilia.utils.message_actor import actor_id


async def channel_destination(client, event, peer, *, posting=False):
    channel = await client.get_chat(normalize_peer(peer) if isinstance(peer, str) else peer)
    if channel.type != ChatType.CHANNEL:
        await event.reply_text(tr("channels.destination_required"))
        return None
    member = await get_chat_member_cached(client, channel.id, bot_id(client), fresh=True)
    if not member_is_present(member):
        await event.reply_text(tr("channels.bot_access_required"))
        return None
    if posting and not member_has_permission(member, "can_post_messages"):
        await event.reply_text(tr("channels.bot_post_required"))
        return None
    if (posting or not channel.username) and not await has_chat_permission(
        client, channel.id, actor_id(event), privilege="can_post_messages" if posting else None
    ):
        await event.reply_text(tr("channels.destination_admin_required"))
        return None
    return channel
