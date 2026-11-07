import logging

import aiohttp
import orjson

from Emilia.config import Config
from Emilia.utils.cache import SimpleCache
from Emilia.utils.http import read_bounded
from Emilia.utils.net_guard import fetch_safe

LOGGER = logging.getLogger(__name__)
_cache = SimpleCache(Config.VANITAS_CACHE_TTL, "vanitas")


async def get_user_info(user_id: int):
    if not Config.VANITAS_API_URL or user_id <= 0:
        return None

    async def load():
        response = await fetch_safe(
            f"{Config.VANITAS_API_URL.rstrip('/')}/user/{int(user_id)}", timeout=10
        )
        try:
            response.raise_for_status()
            data = orjson.loads(await read_bounded(response, 65536))
        finally:
            response.release()
        if not isinstance(data, dict) or not isinstance(data.get("blacklisted"), bool):
            raise ValueError("Invalid antispam response")
        return {
            "blacklisted": data["blacklisted"],
            "reason": data.get("reason") or "",
            "enforcer": data.get("enforcer") or "",
        }

    try:
        return await _cache.get_or_load(str(user_id), load)
    except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
        LOGGER.warning("Antispam lookup failed for %s: %s", user_id, exc)
        return None
