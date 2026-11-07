import io
import re
from dataclasses import dataclass

from aiohttp import ClientError
from pyrogram import enums
from pyrogram.types import LinkPreviewOptions

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import get
from Emilia.utils.message_content import utf16_length

LRCLIB_SEARCH_URL = "https://lrclib.net/api/search"
REQUEST_HEADERS = {
    "User-Agent": Config.HTTP_USER_AGENT,
    "Accept": "application/json,*/*;q=0.8",
}
MAX_TEXT_MESSAGE = 3800


@dataclass
class LyricsResult:
    title: str
    artist: str
    lyrics: str
    source: str
    url: str | None = None


def _strip_synced_timestamps(text: str) -> str:
    return re.sub(r"^\s*\[\d{1,2}:\d{2}(?:\.\d{1,3})?\]\s*", "", text, flags=re.MULTILINE)


def _clean_lyrics(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n?\s*\d*Embed\s*$", "", text, flags=re.IGNORECASE)
    text = text.replace("You might also like", "")
    lines = [line.strip() for line in text.split("\n")]

    cleaned_lines = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                cleaned_lines.append("")
            blank = True
            continue
        cleaned_lines.append(line)
        blank = False

    return "\n".join(cleaned_lines).strip()


def _select_lrclib_result(results: list[dict]) -> dict | None:
    for result in results:
        if result.get("instrumental"):
            continue
        if result.get("plainLyrics") or result.get("syncedLyrics"):
            return result
    return None


async def _fetch_lyrics(query: str) -> LyricsResult | None:
    response = await get(
        LRCLIB_SEARCH_URL,
        params={"q": query},
        headers=REQUEST_HEADERS,
        timeout=12,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, list):
        raise ValueError("Invalid lyrics search response")

    result = _select_lrclib_result(data)
    if not result:
        return None

    lyrics = result.get("plainLyrics") or _strip_synced_timestamps(result.get("syncedLyrics") or "")
    lyrics = _clean_lyrics(lyrics)
    if not lyrics:
        return None

    return LyricsResult(
        title=result.get("trackName") or result.get("name") or query,
        artist=result.get("artistName") or tr("lyrics.unknown_artist"),
        lyrics=lyrics,
        source="LRCLIB",
    )


def _safe_filename(title: str, artist: str) -> str:
    value = f"{artist} - {title}"
    value = re.sub(r"[^A-Za-z0-9._ -]+", "", value).strip(" ._-")
    return (value[:80] or "lyrics") + ".txt"


async def _send_lyrics(message, result: LyricsResult):
    header = tr(
        "lyrics.lyrics_source", artist=result.artist, title=result.title, source=result.source
    )
    if result.url:
        header += f"\n{result.url}"

    body = f"{header}\n\n{result.lyrics}"
    if utf16_length(body) <= MAX_TEXT_MESSAGE:
        return await message.reply_text(
            body,
            parse_mode=enums.ParseMode.DISABLED,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    preview = body.encode("utf-16-le")[: MAX_TEXT_MESSAGE * 2].decode("utf-16-le", errors="ignore")
    preview = preview.rsplit("\n", 1)[0]
    await message.reply_text(
        tr("lyrics.full_lyrics_attached_text_file", preview=preview),
        parse_mode=enums.ParseMode.DISABLED,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )

    with io.BytesIO(body.encode("utf-8")) as lyrics_file:
        lyrics_file.name = _safe_filename(result.title, result.artist)
        await message.reply_document(
            document=lyrics_file,
            caption=tr("lyrics.lyrics", artist=result.artist, title=result.title),
            parse_mode=enums.ParseMode.DISABLED,
        )


@command("lyrics", disable=True)
async def lyrics(_, message):
    query = " ".join(message.command[1:]).strip()
    if not query:
        return await reply_usage(message, lyrics)

    status = await message.reply_text(tr("lyrics.searching_lyrics"))
    try:
        result = await _fetch_lyrics(query)
    except (ClientError, OSError, ValueError):
        LOGGER.exception("Unexpected error while fetching lyrics")
        return await status.edit_text(tr("lyrics.i_could_not_fetch_lyrics_right_now"))
    if not result:
        return await status.edit_text(tr("lyrics.i_could_not_find_lyrics_for_that"))
    await status.delete()
    await _send_lyrics(message, result)
