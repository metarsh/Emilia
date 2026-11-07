import html

from Emilia.custom_filter import command
from Emilia.database.log_channels import set_log_db
from Emilia.locales import tr
from Emilia.utils.channels import channel_destination
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import is_chat_owner
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.forward_origin import fwd_chat


@command("setlog", chat_scope="group", allow_connected=True)
@anonadmin_checker(owner_only=True)
async def set_log(client, message):

    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await is_chat_owner(message, chat_id=chat_id, silent=False):
        return

    forwarded = fwd_chat(message) or fwd_chat(message.reply_to_message)
    peer = (message.command or [])[1:]
    if not forwarded and not peer:
        return await message.reply_text(tr("channels.destination_required"))
    channel = await channel_destination(
        client, message, forwarded.id if forwarded else peer[0], posting=True
    )
    if channel is None:
        return
    await client.send_message(
        channel.id,
        tr("setlog.this_channel_has_been_set_as_the", chat_title=html.escape(chat_title or "Chat")),
    )
    await set_log_db(chat_id, channel.id, channel.title)
    await message.reply_text(
        tr(
            "setlog.successfully_set_log_channel_further_admin_actions_will",
            channel_title=html.escape(channel.title or "Channel"),
        )
    )
