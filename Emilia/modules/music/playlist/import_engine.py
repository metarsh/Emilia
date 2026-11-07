import asyncio
import json
import re
import time
from collections.abc import Callable

import aiohttp
from pyrogram.errors import RPCError

from Emilia.application import LOGGER
from Emilia.locales import tr
from Emilia.modules.music.core.youtube import (
    get_playlist_tracks,
    get_yt_metadata_from_url,
    search_youtube,
)
from Emilia.modules.music.playlist.core import render_bar
from Emilia.utils.http import get_aiohttp_session

_YT_PLAYLIST = re.compile(r"[?&]list=([A-Za-z0-9_-]+)")
_YT_VIDEO = re.compile(
    r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([A-Za-z0-9_-]{11})"
)
_YT_BARE_PLAYLIST = re.compile(r"^(?:PL|UU|OL|RD|LL|FL)[A-Za-z0-9_-]{10,}$")

_SPOTIFY = re.compile(
    r"open\.spotify\.com/(?:intl-[a-z]{2}/)?(playlist|album|track)/([A-Za-z0-9]+)"
)
_SPOTIFY_URI = re.compile(r"spotify:(playlist|album|track):([A-Za-z0-9]+)")

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

_UA = tr("playlist.import.mozilla_5_0_windows_nt_10_0_win64")

MAX_IMPORT = 200
_SEARCH_CONCURRENCY = 4


def detect_source(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    text = text.strip()

    m = _SPOTIFY.search(text) or _SPOTIFY_URI.search(text)
    if m:
        return f"sp_{m.group(1)}", m.group(2)

    m = _YT_PLAYLIST.search(text)
    if m:
        return "yt_playlist", m.group(1)

    m = _YT_VIDEO.search(text)
    if m:
        return "yt_video", m.group(1)

    if _YT_BARE_PLAYLIST.match(text):
        return "yt_playlist", text

    return None, None


_BAR_WIDTH = 12


def render_progress(done: int, total: int, label: str = "Importing") -> str:
    total = max(total, 1)
    pct = min(1.0, done / total)
    bar = render_bar(done, total, _BAR_WIDTH)
    return f"**{label}**\n\n`{bar}`  {int(pct * 100)}%\n`•` {done}/{total} tracks"


class ProgressReporter:
    def __init__(self, message, label: str = "Importing", interval: float = 3.0):
        self._message = message
        self._label = label
        self._interval = interval
        self._last_edit = 0.0
        self._last_text = ""
        self._done = 0
        self._total = 0

    async def update(self, done: int, total: int, force: bool = False):
        self._done, self._total = done, total
        now = time.monotonic()
        if not force and (now - self._last_edit) < self._interval:
            return
        text = render_progress(done, total, self._label)
        if text == self._last_text:
            return
        self._last_edit = now
        self._last_text = text
        try:
            await self._message.edit_text(text)
        except (RPCError, OSError):
            # A failed progress edit must never abort the import itself.
            pass

    async def flush(self):
        await self.update(self._done, self._total, force=True)


async def _fetch(url: str, timeout: int = 20) -> str | None:
    session = await get_aiohttp_session()
    try:
        async with session.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout),
            headers={"User-Agent": _UA, "Accept-Language": "en"},
        ) as resp:
            if resp.status != 200:
                LOGGER.warning(f"[Playlists] fetch {url} -> HTTP {resp.status}")
                return None
            return await resp.text()
    except (aiohttp.ClientError, OSError, UnicodeError) as e:
        LOGGER.warning(f"[Playlists] fetch {url} failed: {e}")
        return None


def _find_entity(data: dict) -> dict | None:
    try:
        entity = data["props"]["pageProps"]["state"]["data"]["entity"]
        if isinstance(entity, dict):
            return entity
    except (KeyError, TypeError):
        pass

    found: list[dict] = []

    def visit(n):
        if found:
            return
        if isinstance(n, dict):
            if n.get("type") in ("track", "album", "playlist") and (
                n.get("title") or n.get("name")
            ):
                found.append(n)
                return
            for v in n.values():
                visit(v)
        elif isinstance(n, list):
            for v in n:
                visit(v)

    visit(data)
    return found[0] if found else None


def _clean(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.replace("\xa0", " ").split())


def _entry_to_track_hint(entry: dict) -> dict | None:
    title = _clean(entry.get("title") or entry.get("name") or "")
    if not title:
        return None

    artist = _clean(entry.get("subtitle") or "")
    if not artist:
        artists = entry.get("artists")
        if isinstance(artists, list) and artists:
            artist = _clean(
                ", ".join(a.get("name") for a in artists if isinstance(a, dict) and a.get("name"))
            )

    duration_ms = entry.get("duration") or 0
    return {
        "query": f"{artist} - {title}" if artist else title,
        "title": title,
        "artist": artist,
        "duration": int(duration_ms // 1000) if duration_ms else 0,
    }


async def fetch_spotify_hints(kind: str, ident: str) -> list[dict]:
    sp_type = kind.split("_", 1)[1]
    html = await _fetch(f"https://open.spotify.com/embed/{sp_type}/{ident}")
    if not html:
        return []

    m = _NEXT_DATA.search(html)
    if not m:
        LOGGER.warning("[Playlists] Spotify embed had no __NEXT_DATA__ payload")
        return []

    try:
        data = json.loads(m.group(1))
    except ValueError as e:
        LOGGER.warning("[Playlists] Spotify payload parse failed: %s", e)
        return []

    entity = _find_entity(data)
    if not entity:
        LOGGER.warning("[Playlists] Spotify embed had no recognisable entity")
        return []

    entries = entity.get("trackList")
    if not isinstance(entries, list) or not entries:
        if entity.get("type") == "track" or kind == "sp_track":
            hint = _entry_to_track_hint(entity)
            return [hint] if hint else []
        return []

    hints = []
    for entry in entries[:MAX_IMPORT]:
        hint = _entry_to_track_hint(entry)
        if hint:
            hints.append(hint)
    return hints


async def _resolve_hint(hint: dict) -> dict | None:
    results = await search_youtube(hint["query"], limit=1)
    if not results:
        return None

    track = dict(results[0])
    track["title"] = f"{hint['artist']} - {hint['title']}" if hint["artist"] else hint["title"]
    if hint["artist"]:
        track["uploader"] = hint["artist"]
    if hint["duration"]:
        track["duration"] = hint["duration"]
    track["source"] = "spotify"
    return track


async def import_from_spotify(
    kind: str,
    ident: str,
    progress: Callable | None = None,
) -> list[dict]:
    queries = await fetch_spotify_hints(kind, ident)
    if not queries:
        return []

    total = len(queries)
    tracks: list[dict] = []
    done = 0
    sem = asyncio.Semaphore(_SEARCH_CONCURRENCY)
    lock = asyncio.Lock()

    async def worker(idx: int, hint: dict):
        nonlocal done
        async with sem:
            track = await _resolve_hint(hint)
        async with lock:
            done += 1
            if track:
                # Keep the original ordering of the Spotify playlist rather than
                # whatever order the searches happen to finish in.
                tracks.append((idx, track))
            if progress:
                try:
                    await progress(done, total)
                except Exception:
                    pass

    await asyncio.gather(*(worker(i, q) for i, q in enumerate(queries)))

    tracks.sort(key=lambda pair: pair[0])
    return [t for _, t in tracks]


async def import_from_youtube(
    kind: str,
    ident: str,
    progress: Callable | None = None,
) -> list[dict]:
    if kind == "yt_video":
        meta = await get_yt_metadata_from_url(f"https://www.youtube.com/watch?v={ident}")
        if progress:
            try:
                await progress(1, 1)
            except Exception:
                pass
        return [meta] if meta else []

    tracks = await get_playlist_tracks(ident, limit=MAX_IMPORT) or []
    if progress:
        try:
            await progress(len(tracks), max(len(tracks), 1))
        except Exception:
            pass
    return tracks


async def import_tracks(
    text: str,
    progress: Callable | None = None,
) -> tuple[list[dict], str | None]:
    kind, ident = detect_source(text)
    if not kind:
        return [], (
            tr("playlist.import.unrecognised_link_supported_youtube_video_playlist_links_spotify")
        )

    try:
        if kind.startswith("sp_"):
            tracks = await import_from_spotify(kind, ident, progress)
            if not tracks:
                return [], (tr("playlist.import.could_not_read_spotify_link_may_private_region"))
        else:
            tracks = await import_from_youtube(kind, ident, progress)
            if not tracks:
                return [], tr("playlist.import.youtube_link_empty_unavailable")
    except Exception as e:
        LOGGER.error(f"[Playlists] import failed for {text!r}: {e}", exc_info=True)
        return [], tr("playlist.import.import_failed_while_resolving_link")

    return tracks[:MAX_IMPORT], None


def source_label(kind: str) -> str:
    return {
        "yt_playlist": tr("playlist.import.youtube_playlist"),
        "yt_video": tr("playlist.import.youtube_track"),
        "sp_playlist": tr("playlist.import.spotify_playlist"),
        "sp_album": tr("playlist.import.spotify_album"),
        "sp_track": tr("playlist.import.spotify_track"),
    }.get(kind, "link")
