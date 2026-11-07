import asyncio
import os
import tempfile
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp
import orjson
from PIL import Image

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.utils.archive import download_bounded
from Emilia.utils.executors import run_in_thread
from Emilia.utils.http import post, read_bounded
from Emilia.utils.tasks import finish_cleanup

TMP_DOWNLOAD_DIRECTORY = str(Path(Config.TEMP_DOWNLOAD_DIRECTORY) / "uploads") + "/"
ZIPLINE_URL = Config.ZIPLINE_URL.rstrip("/")
ZIPLINE_AUTH_URL = (Config.ZIPLINE_AUTH_URL or Config.ZIPLINE_URL).rstrip("/")
ZIPLINE_USERNAME = Config.ZIPLINE_USERNAME
ZIPLINE_PASSWORD = Config.ZIPLINE_PASSWORD
UPLOAD_TIMEOUT = Config.UPLOAD_TIMEOUT
_ZIPLINE_TOKEN_CACHE = None
_ZIPLINE_TOKEN_LOCK = None


def convert_webp_to_png(image_path: Path, output_path: Path) -> None:
    with Image.open(image_path) as image:
        image.save(output_path, "PNG")


async def _login_and_fetch_zipline_token() -> str:
    if not ZIPLINE_USERNAME or not ZIPLINE_PASSWORD:
        raise RuntimeError("Configure ZIPLINE_TOKEN or ZIPLINE_USERNAME and ZIPLINE_PASSWORD.")

    timeout = aiohttp.ClientTimeout(total=UPLOAD_TIMEOUT)
    # Zipline marks login cookies as Secure when CORE_RETURN_HTTPS_URLS=true.
    # Auth must therefore happen via the public HTTPS URL; token uploads can
    # still use the local host-network URL through the Authorization header.
    cookie_jar = aiohttp.CookieJar(unsafe=True)
    async with aiohttp.ClientSession(
        timeout=timeout, cookie_jar=cookie_jar, headers={"User-Agent": Config.HTTP_USER_AGENT}
    ) as session:
        async with session.post(
            f"{ZIPLINE_AUTH_URL}/api/auth/login",
            json={
                "username": ZIPLINE_USERNAME,
                "password": ZIPLINE_PASSWORD,
            },
        ) as response:
            body = (await read_bounded(response, 1024**2)).decode("utf-8", errors="replace")
            if response.status != 200:
                raise RuntimeError(
                    f"Zipline login failed with status {response.status}: "
                    f"{body[:300] or 'empty response'}"
                )

        async with session.get(f"{ZIPLINE_AUTH_URL}/api/user/token") as response:
            body = (await read_bounded(response, 1024**2)).decode("utf-8", errors="replace")
            if response.status != 200:
                raise RuntimeError(
                    f"Zipline token fetch failed with status {response.status}: "
                    f"{body[:300] or 'empty response'}"
                )

    payload = orjson.loads(body or "{}")
    token = payload.get("token") if isinstance(payload, dict) else None
    if not token:
        raise RuntimeError("Zipline token response did not include a token.")
    return str(token)


async def _get_zipline_token() -> str:
    global _ZIPLINE_TOKEN_CACHE, _ZIPLINE_TOKEN_LOCK

    inline_token = Config.ZIPLINE_TOKEN
    if inline_token:
        return inline_token

    if _ZIPLINE_TOKEN_CACHE:
        return _ZIPLINE_TOKEN_CACHE

    if _ZIPLINE_TOKEN_LOCK is None:
        _ZIPLINE_TOKEN_LOCK = asyncio.Lock()

    async with _ZIPLINE_TOKEN_LOCK:
        if _ZIPLINE_TOKEN_CACHE:
            return _ZIPLINE_TOKEN_CACHE
        _ZIPLINE_TOKEN_CACHE = await _login_and_fetch_zipline_token()
        return _ZIPLINE_TOKEN_CACHE


async def upload_local_file(file_path: str, *, cleanup: bool = True) -> str:
    source_path = Path(file_path)
    try:
        if not ZIPLINE_URL:
            raise RuntimeError("Configure ZIPLINE_URL to enable uploads")
        if source_path.stat().st_size > Config.MAX_DOWNLOAD_BYTES:
            raise ValueError("Upload exceeds MAX_DOWNLOAD_BYTES")
        with ExitStack() as resources:
            upload_path = source_path
            if source_path.suffix.lower() == ".webp":
                directory = resources.enter_context(
                    tempfile.TemporaryDirectory(prefix="emilia_upload_")
                )
                upload_path = Path(directory) / (source_path.stem + ".png")
                await finish_cleanup(run_in_thread(convert_webp_to_png, source_path, upload_path))
                if upload_path.stat().st_size > Config.MAX_DOWNLOAD_BYTES:
                    raise ValueError("Converted upload exceeds MAX_DOWNLOAD_BYTES")
            file = resources.enter_context(upload_path.open("rb"))
            form = aiohttp.FormData()
            form.add_field("file", file, filename=upload_path.name)
            response = await post(
                f"{ZIPLINE_URL}/api/upload",
                headers={
                    "authorization": await _get_zipline_token(),
                    "x-zipline-original-name": "true",
                },
                data=form,
                timeout=UPLOAD_TIMEOUT,
                public_only=False,
            )

        if response.status != 200:
            body = (response.text or "").strip()
            raise RuntimeError(
                f"Zipline upload failed with status {response.status or 'no-response'}: "
                f"{body[:300] or 'empty response'}"
            )

        payload = response.json()
        files = payload.get("files") if isinstance(payload, dict) else None
        if not isinstance(files, list) or not files:
            raise RuntimeError(
                f"Zipline upload did not return a file URL: {(response.text or '')[:300]}"
            )

        first_file = files[0]
        url = first_file.get("url") if isinstance(first_file, dict) else None
        if not isinstance(url, str):
            raise RuntimeError("Zipline upload returned an invalid file URL")
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RuntimeError("Zipline upload returned an invalid file URL")
        return url
    finally:
        if cleanup:
            try:
                source_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                LOGGER.warning(
                    f"[Uploader] Failed to remove temp upload file {source_path}: {cleanup_error}"
                )


async def upload(message) -> str:
    os.makedirs(TMP_DOWNLOAD_DIRECTORY, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_DOWNLOAD_DIRECTORY) as directory:
        downloaded = await download_bounded(message._client, message, directory)
        return await upload_local_file(downloaded)
