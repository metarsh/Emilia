import secrets

import orjson

from Emilia.config import Config
from Emilia.locales import tr

_EDIT = """
local queue = cjson.decode(redis.call('GET', KEYS[1]) or '[]')
local action = ARGV[1]
local tracks = cjson.decode(ARGV[2])
local removed = ''
if action == 'append' then
    if #queue + #tracks > tonumber(ARGV[4]) then return {-1, ''} end
    for _, track in ipairs(tracks) do table.insert(queue, track) end
elseif action == 'pop' then
    if #queue > 0 then removed = table.remove(queue, 1) end
elseif action == 'remove' then
    for index, track in ipairs(queue) do
        if cjson.decode(track)['_queue_id'] == tracks then
            removed = table.remove(queue, index)
            break
        end
    end
elseif action == 'merge' then
    local existing = {}
    for _, track in ipairs(queue) do existing[cjson.decode(track)['_queue_id'] or track] = track end
    local merged = {}
    for _, track in ipairs(tracks) do
        local identity = cjson.decode(track)['_queue_id']
        if identity and existing[identity] then
            table.insert(merged, existing[identity])
            existing[identity] = nil
        end
    end
    for _, track in ipairs(queue) do
        if existing[cjson.decode(track)['_queue_id'] or track] then table.insert(merged, track) end
    end
    queue = merged
elseif action == 'reset' then
    if #tracks > tonumber(ARGV[4]) then return {-1, ''} end
    queue = tracks
end
if #queue == 0 then redis.call('DEL', KEYS[1])
else redis.call('SET', KEYS[1], cjson.encode(queue), 'EX', ARGV[3]) end
redis.call('PUBLISH', ARGV[5], ARGV[6])
return {#queue, removed}
"""

_COMPARE = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
if tonumber(ARGV[3]) > 0 then
    redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
else redis.call('SET', KEYS[1], ARGV[2], 'KEEPTTL') end
redis.call('PUBLISH', ARGV[4], ARGV[5])
return 1
"""


def tag_tracks(tracks):
    return [{**track, "_queue_id": secrets.token_hex(12)} for track in tracks]


def _decode_queue(raw):
    tracks = orjson.loads(raw) if raw else []
    if not isinstance(tracks, list):
        raise ValueError("Invalid music queue data")
    return [orjson.loads(track) for track in tracks]


async def _patch_queue(cache, key, transform, ttl=0, *, raw=None):
    """Preserve JSON types and integers; commit only against the read snapshot."""
    from Emilia.application import redis_client

    script = redis_client.register_script(_COMPARE)
    for _ in range(3):
        if raw is None:
            raw = await redis_client.get(cache._rkey(key))
        queue = _decode_queue(raw)
        if not transform(queue):
            return queue
        encoded = orjson.dumps([orjson.dumps(track).decode() for track in queue])
        if await script(
            keys=[cache._rkey(key)],
            args=[
                raw,
                encoded,
                ttl,
                cache._channel_name,
                orjson.dumps({"i": cache._instance_id, "k": key}),
            ],
        ):
            return queue
        raw = None
    raise RuntimeError("The music queue changed repeatedly; please retry")


async def edit_queue(cache, key, action, value, ttl):
    from Emilia.application import redis_client

    if action not in {"append", "pop", "remove", "update", "merge", "reset"}:
        raise ValueError("Unknown queue action")
    if not isinstance(ttl, int) or isinstance(ttl, bool) or ttl <= 0:
        raise ValueError("Queue TTL must be a positive integer")
    if action in {"append", "merge", "reset", "update"}:
        if not isinstance(value, list) or any(
            not isinstance(track, dict) or not track.get("_queue_id") for track in value
        ):
            raise ValueError("Queue tracks require a queue identity")
        if len(value) > Config.MUSIC_MAX_QUEUE_TRACKS:
            raise ValueError(tr("music.queue_full", limit=Config.MUSIC_MAX_QUEUE_TRACKS))
    elif action == "remove":
        if not isinstance(value, str) or not value:
            raise ValueError("Removing a track requires its queue identity")
    elif not isinstance(value, int) or value < 1:
        raise ValueError("Queue positions must be positive integers")
    cache._invalidate(key)
    payload = (
        [orjson.dumps(track).decode() for track in value] if isinstance(value, list) else value
    )
    try:
        if action == "update":
            updates = {track["_queue_id"]: track for track in value}

            def update(queue):
                matched = False
                for track in queue:
                    patch = updates.get(track.get("_queue_id"))
                    if patch is not None:
                        track.update(patch)
                        matched = True
                return matched

            return len(await _patch_queue(cache, key, update, ttl)), None
        count, removed = await redis_client.register_script(_EDIT)(
            keys=[cache._rkey(key)],
            args=[
                action,
                orjson.dumps(payload),
                ttl,
                Config.MUSIC_MAX_QUEUE_TRACKS,
                cache._channel_name,
                orjson.dumps({"i": cache._instance_id, "k": key}),
            ],
        )
    finally:
        cache._invalidate(key)
    if count < 0:
        raise ValueError(tr("music.queue_full", limit=Config.MUSIC_MAX_QUEUE_TRACKS))
    return count, orjson.loads(removed) if removed else None


async def read_queue(cache, key):
    from Emilia.application import redis_client

    raw = await redis_client.get(cache._rkey(key))
    decoded = _decode_queue(raw)
    if any(not track.get("_queue_id") for track in decoded):

        def identify(queue):
            changed = False
            for track in queue:
                if not track.get("_queue_id"):
                    track["_queue_id"] = secrets.token_hex(12)
                    changed = True
            return changed

        cache._invalidate(key)
        try:
            decoded = await _patch_queue(cache, key, identify, raw=raw)
        finally:
            cache._invalidate(key)
    return decoded
