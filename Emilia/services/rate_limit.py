import secrets
from dataclasses import dataclass
from math import isfinite

from Emilia.config import Config

_SLIDING = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + tonumber(clock[2]) / 1000
local window = tonumber(ARGV[2]) * 1000
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now-window)
local count = redis.call('ZCARD', KEYS[1])
if count >= tonumber(ARGV[1]) then
    local first = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return {0, count, math.max(1, math.ceil(tonumber(first[2])+window-now))}
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], math.ceil(window))
return {1, count+1, 0}
"""

_BUCKET = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) * 1000 + tonumber(clock[2]) / 1000
local capacity = tonumber(ARGV[1])
local window = tonumber(ARGV[2]) * 1000
local prior = redis.call('HMGET', KEYS[1], 'tokens', 'updated')
local tokens = tonumber(prior[1]) or capacity
local updated = tonumber(prior[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now-updated)*capacity/window)
local allowed = 0
local retry = 0
if tokens >= 1 then tokens = tokens-1; allowed = 1
else retry = math.ceil((1-tokens)*window/capacity) end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'updated', now)
redis.call('PEXPIRE', KEYS[1], math.ceil(window*2))
return {allowed, math.floor(tokens), retry}
"""


@dataclass(frozen=True)
class LimitResult:
    allowed: bool
    remaining: int
    retry_after: float


async def check_limit(
    key: str, capacity: int, window: float, *, sliding: bool = False
) -> LimitResult:
    if (
        not isinstance(capacity, int)
        or isinstance(capacity, bool)
        or capacity < 1
        or not isinstance(window, (int, float))
        or isinstance(window, bool)
        or not isfinite(window)
        or window <= 0
    ):
        raise ValueError("Rate limits require positive capacity and window")
    from Emilia.application import redis_client

    namespace = Config.CACHE_NAMESPACE or Config.MONGO_DATABASE
    redis_key = f"{namespace}:limit:{'sliding' if sliding else 'bucket'}:{key}"
    script = _SLIDING if sliding else _BUCKET
    arguments = [capacity, window, secrets.token_hex(12)] if sliding else [capacity, window]
    allowed, count, retry = await redis_client.register_script(script)(
        keys=[redis_key], args=arguments
    )
    return LimitResult(
        bool(allowed),
        max(0, capacity - int(count)) if sliding else int(count),
        int(retry) / 1000,
    )


async def claim_notice(key: str, ttl: int = 5) -> bool:
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        raise ValueError("Notice TTL must be a positive integer")
    from Emilia.application import redis_client

    redis_key = f"{Config.CACHE_NAMESPACE or Config.MONGO_DATABASE}:limit_notice:{key}"
    return bool(await redis_client.set(redis_key, "1", nx=True, ex=ttl))
