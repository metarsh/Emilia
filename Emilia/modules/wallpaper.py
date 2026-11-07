import random

from aiohttp import ClientError
from pyrogram.types import ReplyParameters

from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import get


@command("wall", disable=True, rate_limit=Config.RATE_LIMIT_HEAVY)
async def some1(client, message):
    try:
        inpt: str = (
            message.text.split(None, 1)[1]
            if len(message.text) < 3
            else message.text.split(None, 1)[1].replace(" ", "%20")
        )
    except IndexError:
        return await reply_usage(message, some1)

    Emievent = await message.reply_text(tr("wallpaper.sending_please_wait"))
    try:
        r = await get(f"https://bakufuapi.vercel.app/api/wall/wallhaven?query={inpt}&page=1")
        r.raise_for_status()
        r_json = r.json()

        list_id = [r_json["response"][i]["path"] for i in range(len(r_json["response"]))]
        item = (random.sample(list_id, 1))[0]
    except (ClientError, OSError, ValueError, KeyError, TypeError):
        await message.reply_text(tr("wallpaper.try_again_later_or_enter_correct_query"))
        await Emievent.delete()
        return

    await client.send_photo(
        message.chat.id,
        item,
        caption=tr("wallpaper.preview"),
        reply_parameters=ReplyParameters(message_id=message.id),
    )
    await client.send_document(
        message.chat.id,
        item,
        caption=tr("wallpaper.wall"),
        reply_parameters=ReplyParameters(message_id=message.id),
    )
    await Emievent.delete()
