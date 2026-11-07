import logging
import time
from datetime import UTC, datetime, timedelta

from Emilia.application import redis_client
from Emilia.config import Config

PROCESS_START = time.time()

_PREFIX = "metrics"
# Keep daily buckets ~40 days so weekly/monthly rollups always have data.
_DAY_TTL = 40 * 86400

_LEVELS = ("WARNING", "ERROR", "CRITICAL")


def _today_key() -> str:
    return datetime.now(UTC).strftime("%Y%m%d")


def _day_keys(n: int) -> list[str]:
    today = datetime.now(UTC)
    return [(today - timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]


# Command usage (async write path)


async def track_command(command: str) -> None:
    if not command:
        return
    day = _today_key()
    pipe = redis_client.pipeline(transaction=True)
    pipe.incr(f"{_PREFIX}:cmd:total")
    pipe.hincrby(f"{_PREFIX}:cmd:count", command, 1)
    pipe.hincrby(f"{_PREFIX}:cmd:day:{day}", command, 1)
    pipe.expire(f"{_PREFIX}:cmd:day:{day}", _DAY_TTL)
    await pipe.execute()


async def total_commands() -> int:
    value = await redis_client.get(f"{_PREFIX}:cmd:total")
    return int(value) if value else 0


async def top_commands(limit: int = 10) -> list[tuple[str, int]]:
    data = await redis_client.hgetall(f"{_PREFIX}:cmd:count")
    items = sorted(((key, int(value)) for key, value in data.items()), key=lambda item: -item[1])
    return items[:limit]


async def commands_in_days(n: int) -> int:
    pipe = redis_client.pipeline(transaction=False)
    for day in _day_keys(n):
        pipe.hvals(f"{_PREFIX}:cmd:day:{day}")
    return sum(sum(int(value) for value in values) for values in await pipe.execute())


async def log_counts() -> dict[str, int]:
    values = await redis_client.mget([f"{_PREFIX}:log:{level}" for level in _LEVELS])
    return {level: int(value) if value else 0 for level, value in zip(_LEVELS, values, strict=True)}


async def log_counts_days(n: int) -> dict[str, int]:
    out = dict.fromkeys(_LEVELS, 0)
    pipe = redis_client.pipeline(transaction=False)
    for day in _day_keys(n):
        pipe.hmget(f"{_PREFIX}:log:day:{day}", _LEVELS)
    for values in await pipe.execute():
        for level, value in zip(_LEVELS, values, strict=True):
            out[level] += int(value) if value else 0
    return out


_sync_redis = None


def _get_sync_redis():
    global _sync_redis
    if _sync_redis is None:
        import redis as _redis_sync
        from redis.backoff import NoBackoff
        from redis.retry import Retry

        _sync_redis = _redis_sync.from_url(
            Config.REDIS_URL,
            password=Config.REDIS_PASSWORD,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
            max_connections=1,
            retry=Retry(NoBackoff(), 0),
        )
    return _sync_redis


class MetricsLogHandler(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)

    def close(self):
        global _sync_redis
        connection, _sync_redis = _sync_redis, None
        try:
            if connection is not None:
                connection.close()
        finally:
            super().close()

    def emit(self, record: logging.LogRecord) -> None:
        lvl = record.levelname
        if lvl not in _LEVELS:
            return
        day = _today_key()
        pipe = _get_sync_redis().pipeline(transaction=True)
        pipe.incr(f"{_PREFIX}:log:{lvl}")
        pipe.hincrby(f"{_PREFIX}:log:day:{day}", lvl, 1)
        pipe.expire(f"{_PREFIX}:log:day:{day}", _DAY_TTL)
        pipe.execute()
