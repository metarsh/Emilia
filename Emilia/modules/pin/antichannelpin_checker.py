from pyrogram import Client, filters

from Emilia.database.pin import get_antichannelpin
from Emilia.utils.chat_status import bot_has_permission
from Emilia.utils.linked_chat import is_linked_forward


@Client.on_message(filters.all & filters.group, group=7)
async def cleanlinkedChecker(client, message):
    chat_id = message.chat.id
    message_id = message.id
    if not (await get_antichannelpin(chat_id)):
        return

    if await is_linked_forward(client, message):
        if not await bot_has_permission(message, privileges="can_pin_messages", silent=False):
            return
        await client.unpin_chat_message(chat_id=chat_id, message_id=message_id)
