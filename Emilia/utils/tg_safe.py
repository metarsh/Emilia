import asyncio
import logging

from pyrogram.errors import FloodWait

LOGGER = logging.getLogger(__name__)


async def flood_safe(coro_factory, *, retries: int = 3):
    if retries < 1:
        raise ValueError("At least one attempt is required")
    for attempt in range(retries):
        try:
            return await coro_factory()
        except FloodWait as error:
            delay = max(0, float(error.value))
            LOGGER.warning("FloodWait %.1fs (attempt %s)", delay, attempt + 1)
            if attempt == retries - 1:
                raise
            await asyncio.sleep(delay)
