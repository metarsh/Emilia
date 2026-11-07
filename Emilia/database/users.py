# total users/chats

from Emilia.utils.write_buffer import WriteBuffer

WRITE_BUFFER = WriteBuffer()


async def add_user(
    user_id, username=None, chat_id=None, chat_title=None, forwarded=False, bot_id=None
):
    await WRITE_BUFFER.add_user(
        user_id, username, chat_id, chat_title, forwarded=forwarded, bot_id=bot_id
    )


async def add_chat(chat_id, chat_title, bot_id=None):
    await WRITE_BUFFER.add_chat(chat_id, chat_title, bot_id)
