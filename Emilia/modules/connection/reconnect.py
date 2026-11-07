from Emilia.custom_filter import command
from Emilia.database.connection import get_connection
from Emilia.locales import tr
from Emilia.modules.connection.connect import connect_button


@command("reconnect", chat_scope="private")
async def reconnectC(client, message):
    user_id = message.from_user.id
    record = await get_connection(user_id)
    if record and record.get("connected_chat") is not None:
        await connect_button(client, message, record["connected_chat"])
    else:
        await message.reply(tr("reconnect.you_haven_t_made_a_connection_to"))
