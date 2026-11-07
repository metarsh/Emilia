import asyncio
import logging

from Emilia.config import Config

LOGGER = logging.getLogger(__name__)


async def stop_client(client):
    try:
        if getattr(client, "is_initialized", False):
            await asyncio.wait_for(client.stop(), Config.CLONE_STOP_TIMEOUT)
        elif getattr(client, "is_connected", False):
            await asyncio.wait_for(client.disconnect(), Config.CLONE_STOP_TIMEOUT)
    except Exception as exc:
        LOGGER.warning("Telegram client shutdown failed: %s", type(exc).__name__)
    if getattr(client, "is_initialized", False):
        try:
            await asyncio.wait_for(client.terminate(), Config.CLONE_STOP_TIMEOUT)
        except Exception as exc:
            LOGGER.warning("Telegram client termination failed: %s", type(exc).__name__)
    if getattr(client, "is_connected", False):
        try:
            await asyncio.wait_for(client.disconnect(), Config.CLONE_STOP_TIMEOUT)
        except Exception as exc:
            LOGGER.warning("Telegram client disconnect failed: %s", type(exc).__name__)
    if getattr(client, "is_connected", False) or getattr(client, "is_initialized", False):
        raise RuntimeError("Telegram client remains active after shutdown")
