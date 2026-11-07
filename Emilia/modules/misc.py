import random
import sys
import tempfile
from pathlib import Path

from aiohttp import ClientError
from pyrogram.enums import ChatAction
from pyrogram.errors import RPCError
from pyrogram.types import ReplyParameters

from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import get
from Emilia.utils.process import run_process


async def _synthesize_tts(text, lang, path):
    result = await run_process(
        sys.executable,
        "-I",
        "-c",
        "from gtts import gTTS; import sys; gTTS(sys.argv[1], tld='com', lang=sys.argv[2]).save(sys.argv[3])",
        text,
        lang,
        str(path),
        timeout=60,
    )
    if result.returncode:
        raise ValueError("Speech synthesis failed")


@command(pattern="(count|gstat)")
async def ___stat_chat__(client, message):
    await message.reply_text(tr("misc.total_messages", title=message.chat.title, count=message.id))


@command("tts", disable=True, rate_limit=Config.RATE_LIMIT_HEAVY)
async def tts(client, message):
    arguments = (message.text or "").split(None, 1)
    replied = message.reply_to_message
    if replied:
        text = replied.text or replied.caption or ""
        lang = arguments[1].strip().lower() if len(arguments) == 2 else "en"
    elif len(arguments) == 2:
        parts = arguments[1].split(None, 1)
        lang, text = (parts[0].lower(), parts[1]) if len(parts) == 2 else ("en", parts[0])
    else:
        return await reply_usage(message, tts)
    if not text.strip():
        return await reply_usage(message, tts)
    if len(text) > 4096:
        return await message.reply_text(tr("misc.tts_too_long"))
    try:
        with tempfile.TemporaryDirectory(prefix="emilia-tts-") as directory:
            path = Path(directory) / "speech.mp3"
            await _synthesize_tts(text, lang, path)
            result = await run_process(
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
                timeout=10,
            )
            duration = max(1, int(float(result.stdout))) if not result.returncode else 1
            await client.send_chat_action(message.chat.id, ChatAction.RECORD_AUDIO)
            await message.answer_audio(
                str(path),
                duration=duration,
                title=f"stt_{lang}",
                performer=Config.BOT_NAME,
            )
    except (RPCError, OSError, ValueError):
        await message.reply_text(tr("misc.tts_failed"))


@command("gif", disable=True)
async def some(client, message):
    # Parse input safely
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await reply_usage(message, some)
    inpt = parts[1].strip()
    if not inpt:
        return await reply_usage(message, some)

    # Support ';' to specify count, e.g. "cats ; 5"
    count = 1
    if ";" in inpt:
        left, right = inpt.split(";", 1)
        inpt = left.strip()
        try:
            count = int(right.strip())
        except ValueError:
            return await message.reply_text(tr("misc.give_number_of_gifs_between_1_20"))

    # Validate count
    if not inpt:
        return await reply_usage(message, some)
    if not 1 <= count <= 20:
        return await message.reply_text(tr("misc.give_number_of_gifs_between_1_20"))

    if not Config.GIPHY_API_KEY:
        return await message.reply_text(tr("misc.giphy_unconfigured"))

    # Query GIPHY search
    try:
        r = await get(
            "https://api.giphy.com/v1/gifs/search",
            params={"q": inpt, "api_key": Config.GIPHY_API_KEY, "limit": 50},
        )
        if r.status >= 400:
            return await message.reply_text(tr("misc.failed_to_fetch_gifs_try_again_later"))
        js = r.json() or {}
        data = js.get("data", [])
        if not isinstance(data, list) or not data:
            return await message.reply_text(tr("misc.no_gifs_found_for_your_query"))
        gif_urls = []
        for it in data:
            gid = (it or {}).get("id")
            if gid:
                gif_urls.append(f"https://media.giphy.com/media/{gid}/giphy.gif")
    except (ClientError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return await message.reply_text(tr("misc.failed_to_fetch_gifs_try_again_later"))

    if not gif_urls:
        return await message.reply_text(tr("misc.no_gifs_found_for_your_query"))

    # Randomly select up to requested count
    try:
        chosen = random.sample(gif_urls, min(count, len(gif_urls)))
    except ValueError:
        chosen = gif_urls[:count]

    for url in chosen:
        await client.send_animation(
            message.chat.id,
            url,
            reply_parameters=ReplyParameters(message_id=message.id),
        )
