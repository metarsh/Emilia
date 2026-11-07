from Emilia.custom_filter import command
from Emilia.database.connection import disconnectChat, get_connection
from Emilia.locales import tr


@command("disconnect", chat_scope="private")
async def diconnectChat(client, message):
    user_id = message.from_user.id
    record = await get_connection(user_id)
    if record and record.get("connection"):
        await disconnectChat(user_id)
        await message.reply(tr("disconnect.disconnected_from_chat"))
    else:
        await message.reply(tr("disconnect.you_aren_t_connected_to_any_chats"))
