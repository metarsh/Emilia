import io
import random
from contextlib import suppress

import aiohttp
from pyrogram.errors import RPCError

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import post


@command("carbon", disable=True)
async def carbon_image(client, message):
    replied = message.reply_to_message
    if replied and replied.document:
        if replied.document.file_size > Config.CARBON_MAX_CHARACTERS * 4:
            return await message.reply_text(
                tr("carbon.code_too_long", max_chars=Config.CARBON_MAX_CHARACTERS)
            )
        downloaded = await replied.download(in_memory=True)
        if downloaded is None:
            return await reply_usage(message)
        with downloaded:
            try:
                code = downloaded.read().decode("utf-8")
            except UnicodeDecodeError:
                return await reply_usage(message)
    elif replied:
        code = replied.text or replied.caption or ""
    else:
        arguments = (message.text or "").split(None, 1)
        code = arguments[1] if len(arguments) == 2 else ""
    if not code.strip():
        return await reply_usage(message, carbon_image)
    if len(code) > Config.CARBON_MAX_CHARACTERS:
        return await message.reply_text(
            tr("carbon.code_too_long", max_chars=Config.CARBON_MAX_CHARACTERS)
        )
    status = await message.reply_text(tr("carbon.processing"))
    try:
        response = await post(
            Config.CARBON_API_URL,
            json={
                "code": code,
                "language": "python",
                "backgroundColor": random.choice(
                    (
                        "rgba(255, 0, 0, 1)",
                        "rgba(171, 184, 195, 1)",
                        "rgba(255, 255, 0, 1)",
                        "rgba(0, 0, 128, 1)",
                        "rgba(255, 255, 255, 1)",
                    )
                ),
                "fontFamily": random.choice(("Iosevka", "IBM Plex Mono", "hack", "Fira Code")),
                "theme": random.choice(("seti", "night-owl", "one-dark")),
                "exportSize": "2x",
                "fontSize": "14px",
                "lineHeight": "133%",
                "paddingHorizontal": "56px",
                "paddingVertical": "56px",
                "dropShadow": True,
                "dropShadowBlurRadius": "68px",
                "dropShadowOffsetY": "20px",
                "widthAdjustment": True,
                "windowControls": True,
            },
            timeout=30,
        )
        response.raise_for_status()
        if not response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Carbon API did not return a PNG image")
        with io.BytesIO(response.content) as image:
            image.name = "carbon.png"
            await message.reply_photo(image)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        LOGGER.exception("Code image generation failed")
        await message.reply_text(
            tr("carbon.some_error_occured_please_report", support_chat=Config.SUPPORT_CHAT)
        )
    finally:
        with suppress(RPCError):
            await status.delete()
