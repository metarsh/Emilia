import asyncio
import random
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from math import isfinite

import aiohttp
import orjson

from Emilia.config import Config
from Emilia.utils.net_guard import PublicResolver, request_safe

_aiohttp_session = None
_public_session = None
_session_lock = asyncio.Lock()


async def get_aiohttp_session(*, public_only=False) -> aiohttp.ClientSession:
    global _aiohttp_session, _public_session
    async with _session_lock:
        session = _public_session if public_only else _aiohttp_session
        if session is None or session.closed:
            connector = aiohttp.TCPConnector(
                resolver=PublicResolver() if public_only else None,
                ttl_dns_cache=60,
                limit=Config.HTTP_CONNECTION_LIMIT,
                limit_per_host=Config.HTTP_PER_HOST_LIMIT,
            )
            session = aiohttp.ClientSession(
                connector=connector,
                json_serialize=lambda value: orjson.dumps(value).decode(),
                timeout=aiohttp.ClientTimeout(total=30),
                trust_env=False,
                headers={"User-Agent": Config.HTTP_USER_AGENT},
            )
            if public_only:
                _public_session = session
            else:
                _aiohttp_session = session
        return session


async def read_bounded(response, max_bytes=None) -> bytes:
    limit = Config.HTTP_MAX_RESPONSE_BYTES if max_bytes is None else max_bytes
    if limit <= 0:
        raise ValueError("Response size limit must be positive")
    if response.content_length is not None and response.content_length > limit:
        response.close()
        raise ValueError("HTTP response exceeds the size limit")
    body = bytearray()
    async for chunk in response.content.iter_chunked(min(65536, limit + 1)):
        if len(body) + len(chunk) > limit:
            response.close()
            raise ValueError("HTTP response exceeds the size limit")
        body.extend(chunk)
    return bytes(body)


class HTTPResponse:
    def __init__(self, response: aiohttp.ClientResponse, content: bytes):
        self._response = response
        self._content = content

    @property
    def status(self):
        return self._response.status

    @property
    def headers(self):
        return self._response.headers

    @property
    def content(self):
        return self._content

    @property
    def text(self):
        return self._content.decode(self._response.charset or "utf-8", errors="replace")

    def json(self):
        return orjson.loads(self._content)

    def raise_for_status(self):
        self._response.raise_for_status()


def retry_after(headers, fallback: float) -> float:
    value = headers.get("Retry-After")
    if value is None:
        return fallback
    try:
        seconds = float(value)
        return max(0, seconds) if isfinite(seconds) else fallback
    except (TypeError, ValueError):
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return max(0, (when - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return fallback


async def _request(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    timeout: int | float = 15,
    retries: int = 3,
    backoff: float = 1.5,
    max_bytes: int | None = None,
    public_only: bool = True,
    **kwargs,
) -> HTTPResponse:
    attempts = (
        max(1, retries) if method in {"GET", "HEAD", "OPTIONS"} and "data" not in kwargs else 1
    )
    for attempt in range(attempts):
        delay = backoff * (2**attempt) + random.uniform(0, 0.2)
        try:
            if public_only:
                response = await request_safe(
                    method, url, timeout=timeout, headers=headers or {}, **kwargs
                )
            else:
                session = await get_aiohttp_session()
                timeout_cfg = (
                    timeout
                    if isinstance(timeout, aiohttp.ClientTimeout)
                    else aiohttp.ClientTimeout(total=timeout)
                )
                response = await session.request(
                    method,
                    url,
                    timeout=timeout_cfg,
                    headers=headers,
                    allow_redirects=False,
                    **kwargs,
                )
            try:
                result = HTTPResponse(response, await read_bounded(response, max_bytes))
                if response.status not in {429, 500, 502, 503, 504} or attempt == attempts - 1:
                    return result
                delay = retry_after(response.headers, delay)
            finally:
                response.release()
        except (TimeoutError, aiohttp.ClientConnectionError, aiohttp.ClientPayloadError):
            if attempt == attempts - 1:
                raise
        await asyncio.sleep(min(delay, Config.HTTP_RETRY_MAX_DELAY))


async def get(url: str, **kwargs) -> HTTPResponse:
    return await _request("GET", url, **kwargs)


async def post(url: str, **kwargs) -> HTTPResponse:
    return await _request("POST", url, **kwargs)


async def close_http_clients():
    global _aiohttp_session, _public_session
    async with _session_lock:
        for session in (_aiohttp_session, _public_session):
            if session is not None:
                await session.close()
        _aiohttp_session = _public_session = None
