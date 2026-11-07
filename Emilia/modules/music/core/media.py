import asyncio
import os
import tempfile
from pathlib import Path

from Emilia.config import Config


def media_path(filename) -> Path:
    directory = Path(Config.TEMP_DOWNLOAD_DIRECTORY).resolve()
    path = Path(filename).absolute()
    if path.parent.resolve() != directory or path.is_symlink():
        raise ValueError("Music files must be inside the configured download directory")
    return path


def cached_media_path(filename) -> str | None:
    try:
        path = media_path(filename)
        if path.is_file() and 0 < path.stat().st_size <= Config.MUSIC_MAX_DOWNLOAD_BYTES:
            return str(path)
    except (OSError, TypeError, ValueError):
        pass
    return None


async def download_telegram_media(client, message, filename) -> str:
    path = media_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    media = next(
        (
            getattr(message, kind, None)
            for kind in ("audio", "video", "voice", "document")
            if getattr(message, kind, None) is not None
        ),
        None,
    )
    if media is None:
        raise ValueError("Message contains no playable media")
    if (getattr(media, "file_size", 0) or 0) > Config.MUSIC_MAX_DOWNLOAD_BYTES:
        raise ValueError("Music download exceeds the configured size limit")

    async def progress(current, total):
        if max(current, total or 0) > Config.MUSIC_MAX_DOWNLOAD_BYTES:
            raise ValueError("Music download exceeds the configured size limit")

    with tempfile.NamedTemporaryFile(
        prefix=".music-", suffix=path.suffix, dir=path.parent, delete=False
    ) as temporary:
        staging = Path(temporary.name)
    try:
        async with asyncio.timeout(Config.MUSIC_DOWNLOAD_TIMEOUT):
            downloaded = await client.download_media(
                message, file_name=str(staging), progress=progress
            )
        if not downloaded or Path(downloaded).absolute() != staging:
            raise ValueError("Telegram media download failed")
        if cached_media_path(staging) is None:
            raise ValueError("Music download is empty or exceeds the configured size limit")
        os.replace(staging, path)
        return str(path)
    finally:
        staging.unlink(missing_ok=True)
        staging.with_name(staging.name + ".temp").unlink(missing_ok=True)
