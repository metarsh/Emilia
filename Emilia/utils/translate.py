import logging

import aiohttp

from Emilia.config import Config
from Emilia.utils.http import get

LOGGER = logging.getLogger(__name__)


async def translate_text(text: str, target: str) -> str:
    if not text or target.lower() == "en" or len(text) > 5000:
        return text
    try:
        response = await get(
            Config.TRANSLATE_API_URL,
            params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text},
            retries=2,
            max_bytes=1024**2,
        )
        response.raise_for_status()
        segments = response.json()[0]
        if not isinstance(segments, list):
            raise ValueError("Translation response has no text segments")
        translated = "".join(
            segment[0] for segment in segments if segment and isinstance(segment[0], str)
        )
        return translated or text
    except (aiohttp.ClientError, TimeoutError, ValueError, TypeError, IndexError, KeyError):
        LOGGER.warning("Translation unavailable; using the original description")
        return text
