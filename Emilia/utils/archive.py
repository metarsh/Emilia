import asyncio
import stat
import threading
import zipfile
from pathlib import Path, PurePosixPath

from Emilia.config import Config
from Emilia.utils.executors import run_in_thread
from Emilia.utils.tasks import finish_cleanup


class InvalidFileError(ValueError):
    """file validation failure"""


def _check_cancel(cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("Archive operation cancelled")


def create_zip(source, destination, *, cancel_event=None):
    source = Path(source)
    if source.stat().st_size > Config.MAX_DOWNLOAD_BYTES:
        raise InvalidFileError("File exceeds the download size limit")
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        with source.open("rb") as incoming, archive.open(source.name, "w") as outgoing:
            total = 0
            while chunk := incoming.read(65536):
                _check_cancel(cancel_event)
                total += len(chunk)
                if total > Config.MAX_DOWNLOAD_BYTES:
                    raise InvalidFileError("File exceeds the download size limit")
                outgoing.write(chunk)
    if Path(destination).stat().st_size > Config.MAX_ARCHIVE_BYTES:
        raise InvalidFileError("Archive exceeds the size limit")
    return str(destination)


def extract_zip(source, destination, *, cancel_event=None):
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if Path(source).stat().st_size > Config.MAX_DOWNLOAD_BYTES:
        raise InvalidFileError("Archive exceeds the download size limit")
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > Config.MAX_ARCHIVE_FILES:
            raise InvalidFileError("Archive contains too many files")
        targets = set()
        declared_total = 0
        for entry in entries:
            _check_cancel(cancel_event)
            path = PurePosixPath(entry.filename)
            mode = entry.external_attr >> 16
            kind = stat.S_IFMT(mode)
            if (
                not entry.filename
                or "\\" in entry.filename
                or "\x00" in entry.filename
                or path.is_absolute()
                or ".." in path.parts
                or any(":" in part for part in path.parts)
                or kind not in (0, stat.S_IFREG, stat.S_IFDIR)
                or entry.flag_bits & 1
            ):
                raise InvalidFileError("Archive contains an unsafe entry")
            target = (root / path).resolve()
            if target == root or root not in target.parents or target in targets:
                raise InvalidFileError("Archive contains an unsafe or duplicate path")
            targets.add(target)
            if entry.is_dir():
                continue
            declared_total += entry.file_size
            if declared_total > Config.MAX_ARCHIVE_BYTES:
                raise InvalidFileError("Archive expands beyond the size limit")
            if entry.file_size > max(1, entry.compress_size) * Config.MAX_COMPRESSION_RATIO:
                raise InvalidFileError("Archive compression ratio exceeds the limit")

        files = []
        actual_total = 0
        for entry in entries:
            _check_cancel(cancel_event)
            target = (root / entry.filename).resolve()
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as incoming, target.open("xb") as outgoing:
                written = 0
                while chunk := incoming.read(65536):
                    _check_cancel(cancel_event)
                    actual_total += len(chunk)
                    written += len(chunk)
                    if actual_total > Config.MAX_ARCHIVE_BYTES or written > entry.file_size:
                        raise InvalidFileError("Archive expands beyond the size limit")
                    outgoing.write(chunk)
            files.append(str(target))
        return files


async def run_archive(operation, *args):
    cancel_event = threading.Event()
    worker = asyncio.create_task(run_in_thread(operation, *args, cancel_event=cancel_event))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        cancel_event.set()
        try:
            await finish_cleanup(worker)
        except (Exception, asyncio.CancelledError):
            pass
        raise


async def download_bounded(client, reply, destination):
    media = next(
        (
            getattr(reply, name, None)
            for name in (
                "document",
                "video",
                "audio",
                "voice",
                "animation",
                "photo",
                "sticker",
                "video_note",
            )
            if getattr(reply, name, None) is not None
        ),
        None,
    )
    size = getattr(media, "file_size", None)
    if media is None or size is None:
        raise InvalidFileError("Reply to a downloadable file")
    if size > Config.MAX_DOWNLOAD_BYTES:
        raise InvalidFileError("File exceeds the download size limit")
    exceeded = False

    async def progress(current, total):
        nonlocal exceeded
        if current > Config.MAX_DOWNLOAD_BYTES or total > Config.MAX_DOWNLOAD_BYTES:
            exceeded = True
            client.stop_transmission()

    filename = Path(getattr(media, "file_name", None) or "file").name
    if filename in {"", ".", ".."}:
        filename = "file"
    async with asyncio.timeout(120):
        downloaded = await reply.download(
            file_name=str(Path(destination) / filename), progress=progress
        )
    if exceeded or not downloaded:
        raise InvalidFileError("Download failed or exceeded the size limit")
    path = Path(downloaded).resolve()
    root = Path(destination).resolve()
    if root not in path.parents or path.stat().st_size > Config.MAX_DOWNLOAD_BYTES:
        raise InvalidFileError("Downloaded file exceeds the size limit")
    return str(path)
