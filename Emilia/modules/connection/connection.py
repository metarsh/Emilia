from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.modules.connection.connect import show_connection
from Emilia.utils.connections import connection


@command("connection", chat_scope="private")
async def ConnectionChat(client, message):
    if await connection(message) is None:
        return await message.reply(tr("connection.you_aren_t_connected_to_any_chat"))
    await show_connection(client, message, message._emilia_target_chat)
