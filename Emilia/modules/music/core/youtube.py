import asyncio
import logging
import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import yt_dlp
from pyrogram.errors import RPCError
from redis.exceptions import RedisError

from Emilia.application import pgram
from Emilia.config import Config
from Emilia.modules.music.core.media import cached_media_path, download_telegram_media
from Emilia.modules.music.utils.store import (
    get_active_media_paths,
    get_cached_media,
    get_cached_meta,
    set_cached_media,
    set_cached_meta,
)
from Emilia.utils.tasks import spawn

LOGGER = logging.getLogger(__name__)


_search_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="YTSearch")
_download_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="YTDownload")
_COOKIES = Config.COOKIES_FILE
_STOPPING = threading.Event()


class ReadOnlyCookieYoutubeDL(yt_dlp.YoutubeDL):
    def save_cookies(self):
        pass


if os.path.isfile(_COOKIES):
    LOGGER.info("[Music] Using YouTube cookie file: %s", _COOKIES)
else:
    LOGGER.warning(
        "[Music] YouTube cookie file not found at %s — downloads may be rate-limited or blocked by YouTube.",
        _COOKIES,
    )

_CLEANUP_INTERVAL = 3600  # run cleanup every hour
_MAX_FILE_AGE_HOURS = Config.MUSIC_DOWNLOAD_MAX_AGE_HOURS


def _build_ydl_opts(extract_audio=True, is_video=False, use_cookies=True, *, cancel_event=None):
    def check_cancelled(*args, **kwargs):
        if _STOPPING.is_set() or (cancel_event is not None and cancel_event.is_set()):
            raise yt_dlp.utils.DownloadError("YouTube operation cancelled")

    def check_progress(data):
        check_cancelled()
        if (
            max(data.get("downloaded_bytes") or 0, data.get("total_bytes") or 0)
            > Config.MUSIC_MAX_DOWNLOAD_BYTES
        ):
            raise yt_dlp.utils.DownloadError("Music download exceeds the configured size limit")

    opts = {
        "quiet": True,
        "no_warnings": True,
        "cookiefile": _COOKIES if (use_cookies and _COOKIES and os.path.isfile(_COOKIES)) else None,
        "noplaylist": True,
        "extract_flat": "in_playlist",
        "js_runtimes": {"node": {}},
        "concurrent_fragments": 4,
        "buffer_size": "16K",
        "resize_buffer": True,
        "socket_timeout": 15,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "max_filesize": Config.MUSIC_MAX_DOWNLOAD_BYTES,
        "match_filter": check_cancelled,
        "progress_hooks": [check_progress],
        "postprocessor_hooks": [check_cancelled],
        "extractor_args": {
            "youtube": {
                "player_client": [
                    "web_safari",
                    "tv_downgraded",
                    "android_vr",
                    "mweb",
                    "web",
                    "ios",
                ],
            }
        },
    }
    if is_video:
        opts.update(
            {
                "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/bestvideo+bestaudio/best/best*",
                "merge_output_format": "mp4",
                "outtmpl": os.path.join(Config.TEMP_DOWNLOAD_DIRECTORY, "%(id)s.%(ext)s"),
            }
        )
        if shutil.which("ffmpeg"):
            opts["postprocessors"] = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]
    elif extract_audio:
        opts.update(
            {
                "format": "bestaudio/best",
                "outtmpl": os.path.join(Config.TEMP_DOWNLOAD_DIRECTORY, "%(id)s.%(ext)s"),
            }
        )
    return opts


def _youtube_url(url):
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.hostname
        in {
            "youtube.com",
            "www.youtube.com",
            "music.youtube.com",
            "m.youtube.com",
            "youtu.be",
            "www.youtu.be",
        }
        and not parts.username
        and not parts.password
        and parts.port in (None, 443)
    )


async def _yt_run(func, *args, executor=None, **kwargs):
    if _STOPPING.is_set():
        raise RuntimeError("YouTube workers are shutting down")
    loop = asyncio.get_running_loop()
    pool = executor or _search_executor
    cancel_event = threading.Event()

    def run():
        if _STOPPING.is_set() or cancel_event.is_set():
            raise yt_dlp.utils.DownloadError("YouTube operation cancelled")
        return func(*args, cancel_event=cancel_event, **kwargs)

    worker = loop.run_in_executor(pool, run)
    worker.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
    timeout = (
        Config.MUSIC_DOWNLOAD_TIMEOUT
        if pool is _download_executor
        else Config.MUSIC_METADATA_TIMEOUT
    )
    try:
        async with asyncio.timeout(timeout):
            return await asyncio.shield(worker)
    except (TimeoutError, asyncio.CancelledError):
        cancel_event.set()
        raise


async def search_youtube(query: str, limit: int = 8):
    def _search(*, cancel_event):
        with ReadOnlyCookieYoutubeDL(
            _build_ydl_opts(extract_audio=False, cancel_event=cancel_event)
        ) as ydl:
            results = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
            return results.get("entries", []) if results else []

    try:
        entries = await _yt_run(_search)
        candidates = []
        for entry in entries:
            vid = entry.get("id", "")
            candidates.append(
                {
                    "id": vid,
                    "title": entry.get("title", "Unknown"),
                    "uploader": entry.get("channel", "YouTube"),
                    "thumbnail": entry.get("thumbnail")
                    or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                    "duration": entry.get("duration") or 0,
                    "webpage_url": entry.get(
                        "webpage_url", f"https://www.youtube.com/watch?v={vid}"
                    ),
                    "source": "youtube",
                }
            )
        return candidates
    except (yt_dlp.utils.YoutubeDLError, OSError, RuntimeError) as e:
        LOGGER.warning("[Music] YouTube search failed: %s", e)
        return []


async def get_yt_metadata_from_url(url: str):
    if not _youtube_url(url):
        raise ValueError("Use an HTTPS YouTube URL")

    def _meta(*, cancel_event):
        with ReadOnlyCookieYoutubeDL(
            _build_ydl_opts(extract_audio=False, cancel_event=cancel_event)
        ) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await _yt_run(_meta)
        if not info:
            return None
        vid = info.get("id", "")
        return {
            "id": vid,
            "title": info.get("title", "Unknown"),
            "uploader": info.get("channel", "YouTube"),
            "thumbnail": info.get("thumbnail") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            "duration": info.get("duration") or 0,
            "webpage_url": info.get("webpage_url", f"https://www.youtube.com/watch?v={vid}"),
            "source": "youtube",
        }
    except (yt_dlp.utils.YoutubeDLError, OSError, RuntimeError) as e:
        LOGGER.warning("[Music] YouTube metadata fetch failed: %s", e)
        return None


async def download_youtube_audio(
    url: str, video_id: str, is_video: bool = False, progress_callback=None
) -> str | None:
    if not _youtube_url(url) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", video_id):
        raise ValueError("Invalid YouTube track")
    directory = Path(Config.TEMP_DOWNLOAD_DIRECTORY)
    if any(path.is_symlink() for path in directory.glob(f"{video_id}.*")):
        raise ValueError("Music cache entries must not be symlinks")
    loop = asyncio.get_running_loop()

    def _download(*, cancel_event):
        opts = _build_ydl_opts(
            extract_audio=not is_video, is_video=is_video, cancel_event=cancel_event
        )
        opts["outtmpl"] = os.path.join(Config.TEMP_DOWNLOAD_DIRECTORY, f"{video_id}.%(ext)s")
        if progress_callback:

            class ProgressHook:
                def __init__(self):
                    self.last_bytes = 0

                def __call__(self, d):
                    if d.get("status") == "downloading":
                        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                        downloaded = d.get("downloaded_bytes", 0)
                        if total > 0:
                            pct = downloaded / total
                            loop.call_soon_threadsafe(progress_callback, downloaded, total, pct)

            opts["progress_hooks"].append(ProgressHook())
        with ReadOnlyCookieYoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info:
                return ydl.prepare_filename(info)
        return None

    try:
        filename = await _yt_run(_download, executor=_download_executor)
        if filename and os.path.exists(filename):
            size = os.path.getsize(filename)
            if size > Config.MUSIC_MAX_DOWNLOAD_BYTES:
                Path(filename).unlink()
                raise ValueError("Music download exceeds the configured size limit")
            local_path = cached_media_path(filename)
            if local_path is None:
                raise ValueError("Invalid downloaded music path")
            LOGGER.info("[Music] Downloaded %s to %s (%d bytes)", video_id, local_path, size)
            return local_path
        LOGGER.error("[Music] YouTube download failed: file not found after download")
    except (yt_dlp.utils.YoutubeDLError, OSError, RuntimeError, ValueError) as e:
        LOGGER.error("[Music] YouTube download failed for %s: %s", video_id, e)

    return None


async def _upload_to_event_logs(
    file_path: str, track_info: dict, is_video: bool = False
) -> int | None:
    try:
        caption = f"{track_info.get('title', 'Unknown')} - {track_info.get('uploader', 'YouTube')}"
        duration = int(track_info.get("duration", 0) or 0)
        if is_video:
            # Video mode (/vplay): upload as video first
            try:
                msg = await pgram.send_video(
                    chat_id=Config.EVENT_LOGS,
                    video=file_path,
                    caption=caption,
                    duration=duration,
                )
                if msg:
                    return msg.id
            except (RPCError, OSError) as e:
                LOGGER.debug("[Music] send_video upload to EVENT_LOGS fallback: %s", e)
        else:
            # Audio mode (/play): upload as audio first (native audio player with metadata)
            try:
                msg = await pgram.send_audio(
                    chat_id=Config.EVENT_LOGS,
                    audio=file_path,
                    title=track_info.get("title", "Unknown"),
                    performer=track_info.get("uploader", "YouTube"),
                    duration=duration,
                )
                if msg:
                    return msg.id
            except (RPCError, OSError) as e:
                LOGGER.debug("[Music] send_audio upload to EVENT_LOGS fallback: %s", e)

        # Fallback to send_document if specific media upload fails
        msg = await pgram.send_document(
            chat_id=Config.EVENT_LOGS,
            document=file_path,
            caption=caption,
        )
        if msg:
            return msg.id
    except (RPCError, OSError, ValueError) as e:
        LOGGER.warning("[Music] Failed to upload to EVENT_LOGS: %s", e)
    return None


async def _cache_media_background(local_path: str, track_info: dict, video_id: str, is_video: bool):
    try:
        await asyncio.sleep(5)  # Let VC stabilize before background upload
        message_id = await _upload_to_event_logs(local_path, track_info, is_video)
        if message_id:
            ext = os.path.splitext(local_path)[1].lstrip(".") or ("mp4" if is_video else "m4a")
            await set_cached_media(video_id, {"message_id": message_id, "extension": ext}, is_video)
        else:
            LOGGER.warning(
                "[Music] Background cache failed for %s (%s): no file_id returned",
                video_id,
                track_info.get("title"),
            )
    except (RPCError, RedisError, OSError, ValueError) as e:
        LOGGER.warning(
            "[Music] Background cache failed for %s (%s): %s", video_id, track_info.get("title"), e
        )


def cleanup_old_downloads(
    max_age_hours: int = _MAX_FILE_AGE_HOURS, active_paths: set | None = None
) -> int:
    directory = Path(Config.TEMP_DOWNLOAD_DIRECTORY)
    if not directory.is_dir():
        return 0
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    deleted = 0
    files = []
    total_size = 0
    for path in directory.iterdir():
        fpath = str(path)
        if (
            path.is_symlink()
            or not path.is_file()
            or path.suffix.lower()
            not in {
                ".mp3",
                ".m4a",
                ".mp4",
                ".webm",
                ".mkv",
                ".opus",
                ".ogg",
                ".part",
                ".temp",
                ".ytdl",
            }
        ):
            continue
        try:
            mtime = os.path.getmtime(fpath)
            size = os.path.getsize(fpath)
            total_size += size
            if active_paths and os.path.abspath(fpath) in active_paths:
                continue
            files.append((fpath, datetime.fromtimestamp(mtime), size))
        except (OSError, OverflowError, ValueError):
            pass

    remaining_files = []
    for fpath, mtime, size in files:
        if mtime < cutoff:
            try:
                os.remove(fpath)
                deleted += 1
                total_size -= size
                LOGGER.info("[Music] Cleaned old file: %s", fpath)
            except OSError as e:
                LOGGER.warning("[Music] Failed to delete %s: %s", fpath, e)
        else:
            remaining_files.append((fpath, mtime, size))

    max_dir_size = Config.MUSIC_DOWNLOAD_CACHE_BYTES
    target_dir_size = max_dir_size * 4 // 5
    if total_size > max_dir_size:
        remaining_files.sort(key=lambda x: x[1])
        for fpath, _mtime, size in remaining_files:
            if total_size <= target_dir_size:
                break
            if Path(fpath).suffix.lower() in {".part", ".temp", ".ytdl"}:
                continue
            try:
                os.remove(fpath)
                deleted += 1
                total_size -= size
                LOGGER.info("[Music] Size cleanup removed old file: %s", fpath)
            except OSError as e:
                LOGGER.warning("[Music] Failed to delete for size cleanup %s: %s", fpath, e)

    return deleted


def start_cleanup_task():
    async def _loop():
        while True:
            await asyncio.sleep(_CLEANUP_INTERVAL)
            try:
                active_paths = await get_active_media_paths()
                count = await asyncio.to_thread(cleanup_old_downloads, active_paths=active_paths)
                if count:
                    LOGGER.info("[Music] Cleanup removed %d old files", count)
            except (RedisError, OSError) as e:
                LOGGER.warning("[Music] Cleanup task error: %s", e)

    return _loop()


async def _resolve_file(track_info: dict, progress_callback=None):
    video_id = track_info["id"]
    if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", video_id):
        raise ValueError("Invalid music track identifier")
    is_video = track_info.get("is_video", False)
    directory = Path(Config.TEMP_DOWNLOAD_DIRECTORY)
    directory.mkdir(parents=True, exist_ok=True)

    possible_exts = ("mp4", "mkv", "webm") if is_video else ("m4a", "webm", "mp3", "opus", "mp4")
    for ext in possible_exts:
        path = directory / f"{video_id}.{ext}"
        local_path = cached_media_path(path)
        if local_path:
            LOGGER.info("[Music] Local disk HIT for %s (%s). Instant stream!", video_id, local_path)
            track_info["file_path"] = local_path
            return track_info

    cached_val = await get_cached_media(video_id, is_video)
    if cached_val:
        LOGGER.info("[Music] Telegram cache HIT for %s.", video_id)
        if isinstance(cached_val, str):
            parts = cached_val.split("|")
            cached_val = (
                {"message_id": int(parts[0]), "extension": parts[1]}
                if (len(parts) == 2 and parts[0].isdigit())
                else {}
            )
        message_id = cached_val.get("message_id") if isinstance(cached_val, dict) else None
        ext = cached_val.get("extension") if isinstance(cached_val, dict) else None
        if isinstance(message_id, int) and ext in {*possible_exts, "ogg"}:
            local_path = str((directory / f"{video_id}.{ext}").absolute())
            try:
                async with asyncio.timeout(Config.MUSIC_METADATA_TIMEOUT):
                    msg = await pgram.get_messages(Config.EVENT_LOGS, message_id)
                if msg:
                    track_info["file_path"] = await download_telegram_media(pgram, msg, local_path)
                    return track_info
            except (RPCError, OSError, ValueError) as e:
                LOGGER.warning(
                    "[Music] Failed to fetch message/download media from EVENT_LOGS for %s: %s",
                    video_id,
                    e,
                )

    url = f"https://www.youtube.com/watch?v={video_id}"

    local_path = await download_youtube_audio(
        url, video_id, is_video=is_video, progress_callback=progress_callback
    )
    if not local_path:
        raise ValueError("Could not download audio for this track.")

    track_info["file_path"] = local_path

    if not await get_cached_media(video_id, is_video):
        spawn(
            _cache_media_background(local_path, track_info, video_id, is_video),
            name=f"media_cache:{video_id}:{is_video}",
        )

    return track_info


async def ensure_local_file(track_info: dict) -> dict:
    path = track_info.get("file_path")
    if path and cached_media_path(path):
        return track_info
    if track_info.get("source") == "telegram":
        raise ValueError("The Telegram media is no longer cached; send it again")
    return await _resolve_file(track_info)


async def fetch_and_download(query: str, is_video: bool = False, progress_callback=None):
    norm = query.strip().lower()
    cached_meta = await get_cached_meta(norm)
    if cached_meta:
        track_info = dict(cached_meta)
    else:
        if query.startswith("http"):
            track_info = await get_yt_metadata_from_url(query)
        else:
            results = await search_youtube(query, limit=1)
            track_info = results[0] if results else None
        if not track_info:
            raise ValueError("Could not find any YouTube results for this query.")
        await set_cached_meta(norm, track_info)

    track_info["is_video"] = is_video
    return await _resolve_file(track_info, progress_callback=progress_callback)


async def resolve_audio(candidate: dict, is_video: bool = False, progress_callback=None):
    track_info = dict(candidate)
    track_info["is_video"] = is_video
    return await _resolve_file(track_info, progress_callback=progress_callback)


async def get_playlist_tracks(playlist_id: str, limit: int = 100):
    def _fetch(*, cancel_event):
        opts = _build_ydl_opts(extract_audio=False, cancel_event=cancel_event)
        opts["extract_flat"] = True
        opts["noplaylist"] = False
        url = f"https://www.youtube.com/playlist?list={playlist_id}"
        with ReadOnlyCookieYoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []
            entries = info.get("entries", [])[:limit]
            tracks = []
            for entry in entries:
                vid = entry.get("id", "")
                tracks.append(
                    {
                        "id": vid,
                        "title": entry.get("title", "Unknown"),
                        "uploader": entry.get("channel", "YouTube"),
                        "thumbnail": entry.get("thumbnail")
                        or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                        "duration": entry.get("duration") or 0,
                        "webpage_url": entry.get(
                            "webpage_url", f"https://www.youtube.com/watch?v={vid}"
                        ),
                        "source": "youtube",
                    }
                )
            return tracks

    try:
        return await _yt_run(_fetch)
    except (yt_dlp.utils.YoutubeDLError, OSError, RuntimeError) as e:
        LOGGER.warning("[Music] YouTube playlist fetch failed: %s", e)
        return []


async def get_related_tracks(video_id: str, limit: int = 25) -> list[dict]:
    if not video_id:
        return []

    cache_key = f"related:{video_id}"
    cached = await get_cached_meta(cache_key)
    if cached:
        return list(cached)

    def _fetch(*, cancel_event):
        opts = _build_ydl_opts(extract_audio=False, cancel_event=cancel_event)
        opts["extract_flat"] = True
        opts["noplaylist"] = False
        opts["playlist_items"] = f"1:{limit + 1}"
        url = f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}"
        with ReadOnlyCookieYoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return []
            entries = info.get("entries", [])
            tracks = []
            for entry in entries:
                vid = entry.get("id", "")
                if not vid or vid == video_id:
                    continue
                tracks.append(
                    {
                        "id": vid,
                        "title": entry.get("title", "Unknown"),
                        "uploader": entry.get("channel", "YouTube"),
                        "thumbnail": entry.get("thumbnail")
                        or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                        "duration": entry.get("duration") or 0,
                        "webpage_url": entry.get(
                            "webpage_url", f"https://www.youtube.com/watch?v={vid}"
                        ),
                        "source": "youtube",
                    }
                )
                if len(tracks) >= limit:
                    break
            return tracks

    try:
        results = await _yt_run(_fetch)
        if results:
            await set_cached_meta(cache_key, results)
        return results or []
    except (yt_dlp.utils.YoutubeDLError, RedisError, OSError, RuntimeError) as e:
        LOGGER.warning("[Music] YouTube related tracks fetch failed for %s: %s", video_id, e)
        return []


async def shutdown_youtube():
    _STOPPING.set()
    await asyncio.to_thread(_search_executor.shutdown, wait=True, cancel_futures=True)
    await asyncio.to_thread(_download_executor.shutdown, wait=True, cancel_futures=True)
