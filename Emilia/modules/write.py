import io
from contextlib import suppress

from pyrogram.errors import RPCError

from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import get


@command("write", disable=True, rate_limit=Config.RATE_LIMIT_HEAVY)
async def writer(client, message):
    if message.reply_to_message_id:
        text = message.reply_to_message.text if message.reply_to_message else None
        if not text:
            return await reply_usage(message)
    else:
        arguments = message.text.split(maxsplit=1)
        if len(arguments) < 2:
            return await reply_usage(message)
        text = arguments[1]
    status = await message.reply_text(tr("write.waitoo"))
    try:
        response = await get("https://apis.xditya.me/write", params={"text": text})
        response.raise_for_status()
        with io.BytesIO(response.content) as image:
            image.name = "handwriting.png"
            await message.reply_photo(image)
    finally:
        with suppress(RPCError):
            await status.delete()
