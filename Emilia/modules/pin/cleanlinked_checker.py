from pyrogram import Client, filters

from Emilia.database.pin import get_cleanlinked
from Emilia.locales import tr
from Emilia.utils.chat_status import bot_has_permission
from Emilia.utils.linked_chat import is_linked_forward


@Client.on_message(filters.all & filters.group, group=6)
async def cleanlinkedChecker(client, message):
    chat_id = message.chat.id
    if not (await get_cleanlinked(chat_id)):
        return

    if await is_linked_forward(client, message):
        if await bot_has_permission(message, privileges="can_delete_messages", silent=True):
            await message.delete()
        else:
            await message.reply(tr("cleanlinked_checker.i_don_t_have_the_right_to"))
