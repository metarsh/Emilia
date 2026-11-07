import secrets
from dataclasses import dataclass
from math import isfinite

from Emilia.application import redis_client
from Emilia.config import Config
from Emilia.utils.client_context import bot_id

MAX_HISTORY = 1000
MAX_WINDOW = 86400

_RECORD = """
local user = ARGV[1]
local message = ARGV[2]
local limit = tonumber(ARGV[3])
local window = tonumber(ARGV[4])
local timed = ARGV[5] == '1'
local exempt = ARGV[6] == '1'
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
if timed then
    if exempt then return {} end
    redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now-window)
    redis.call('ZADD', KEYS[1], now, message)
else
    redis.call('ZADD', KEYS[1], tonumber(message), user..':'..message)
end
local size = redis.call('ZCARD', KEYS[1])
if size > 1000 then redis.call('ZREMRANGEBYRANK', KEYS[1], 0, size-1001) end
redis.call('EXPIRE', KEYS[1], math.ceil(math.max(60, window)+10))
if exempt or size < limit then return {} end
if not timed then
    local recent = redis.call('ZREVRANGE', KEYS[1], 0, limit-1)
    for _, member in ipairs(recent) do
        if string.match(member, '^([^:]+):') ~= user then return {} end
    end
end
if not redis.call('SET', KEYS[2], ARGV[7], 'NX', 'EX', 60) then return {} end
local members = redis.call('ZREVRANGE', KEYS[1], 0, 999)
local matches = {}
for _, member in ipairs(members) do
    if not timed and string.match(member, '^([^:]+):') ~= user then break end
    table.insert(matches, member)
end
return matches
"""

_FINISH = """
if redis.call('GET', KEYS[2]) ~= ARGV[1] then return 0 end
if ARGV[2] == '0' then
    redis.call('DEL', KEYS[2])
    return 1
end
local ttl = redis.call('PTTL', KEYS[1])
for index=5,#ARGV do redis.call('ZREM', KEYS[1], ARGV[index]) end
if ARGV[3] == '0' then
    redis.call('ZADD', KEYS[1], tonumber(ARGV[4]), '0:'..ARGV[4])
    redis.call('PEXPIRE', KEYS[1], math.max(1, ttl))
end
return 1
"""

_record_script = redis_client.register_script(_RECORD)
_finish_script = redis_client.register_script(_FINISH)


@dataclass(frozen=True)
class FloodDetection:
    history_key: str
    claim_key: str
    token: str
    members: tuple[str, ...]
    timed: bool

    @property
    def message_ids(self):
        return [int(member.rsplit(":", 1)[-1]) for member in self.members]


async def record_message(
    client, chat_id, user_id, message_id, *, threshold, window=60, timed=False, exempt=False
):
    if (
        not isinstance(threshold, int)
        or isinstance(threshold, bool)
        or not 1 <= threshold <= MAX_HISTORY
        or not isinstance(window, (int, float))
        or isinstance(window, bool)
        or not isfinite(window)
        or not 0 < window <= MAX_WINDOW
    ):
        raise ValueError("Flood thresholds and windows exceed the supported bounds")
    prefix = f"{Config.CACHE_NAMESPACE}:flood:{bot_id(client)}:{chat_id}"
    history_key = f"{prefix}:window:{user_id}" if timed else f"{prefix}:consecutive"
    claim_key = f"{prefix}:punish:{user_id}"
    token = secrets.token_hex(16)
    members = await _record_script(
        keys=[history_key, claim_key],
        args=[user_id, message_id, threshold, window, int(timed), int(exempt), token],
    )
    if not members:
        return None
    return FloodDetection(history_key, claim_key, token, tuple(members), timed)


async def finish_detection(detection, *, succeeded):
    return await _finish_script(
        keys=[detection.history_key, detection.claim_key],
        args=[
            detection.token,
            int(succeeded),
            int(detection.timed),
            max(detection.message_ids),
            *detection.members,
        ],
    )
