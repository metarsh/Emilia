from aiohttp import ClientError
from pyrogram.errors import RPCError

from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.http import get


@command(["joke", "jokes", "funny"], disable=True)
async def joke(client, message):
    try:
        response = await get("https://v2.jokeapi.dev/joke/Any")
        response.raise_for_status()
        joke = response.json()
        if joke["type"] == "twopart":
            get1 = joke["setup"]
            get2 = joke["delivery"]
            text = tr("joke.joke_get1_get2", get1=get1, get2=get2)
        else:
            text = joke["joke"]
        await message.reply(text)
    except (ClientError, RPCError, OSError, ValueError, KeyError, TypeError):
        return await message.reply_text(tr("joke.unavailable"))
