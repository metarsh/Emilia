import io
from urllib.parse import quote

from pyrogram.types import Message

from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import read_bounded
from Emilia.utils.net_guard import fetch_safe


@command("webss", disable=True, rate_limit=Config.RATE_LIMIT_HEAVY)
async def take_ss(client, message: Message):
    if len(message.text.split()) != 2:
        return await reply_usage(message, take_ss)
    url = message.text.split(None, 1)[1]
    if "://" not in url:
        url = "https://" + url
    try:
        target = await fetch_safe(url)
        try:
            target.raise_for_status()
            url = str(target.url)
        finally:
            target.close()
        screenshot = await fetch_safe(
            "https://service.headless-render-api.com/screenshot/" + quote(url, safe="")
        )
        try:
            screenshot.raise_for_status()
            content = await read_bounded(screenshot)
        finally:
            screenshot.release()
    except ValueError:
        return await message.reply_text(tr("webshot.that_url_is_not_allowed_or_exceeds"))
    with io.BytesIO(content) as photo:
        photo.name = "screenshot.png"
        return await message.reply_photo(photo)
