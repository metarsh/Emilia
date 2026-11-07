from Emilia.config import Config
from Emilia.services.music_queue import edit_queue, read_queue, tag_tracks
from Emilia.utils.cache import SimpleCache

QUEUE_TTL = 7200  # live player state expires if a chat goes idle (2h)
FILE_TTL = 60 * 60 * 24 * 365 * 10  # Retain cached Telegram file IDs for ten years.
META_TTL = 60 * 60 * 24  # resolved YouTube metadata per query

music_state = SimpleCache(
    default_ttl=QUEUE_TTL,
    namespace=f"music_q:{Config.BOT_ID}",
)
music_cache = SimpleCache(
    default_ttl=FILE_TTL,
    namespace=f"music_file_v2:{Config.BOT_ID}",
)
music_meta = SimpleCache(default_ttl=META_TTL, namespace="music_meta")
music_menu = SimpleCache(
    default_ttl=300,
    namespace=f"music_menu:{Config.BOT_ID}",
)


async def get_active_media_paths() -> set[str]:
    import os

    import orjson

    from Emilia.application import redis_client

    paths = set()

    async def read_paths(keys):
        for raw in await redis_client.mget(keys):
            if raw is None:
                continue
            data = orjson.loads(raw)
            tracks = data if isinstance(data, list) else [data]
            for track in tracks:
                if isinstance(track, str):
                    track = orjson.loads(track)
                if isinstance(track, dict) and track.get("file_path"):
                    paths.add(os.path.abspath(track["file_path"]))

    for prefix in ("now", "queue", "autoplay_q"):
        keys = []
        async for key in redis_client.scan_iter(match=music_state._rkey(f"{prefix}:*"), count=200):
            keys.append(key)
            if len(keys) == 200:
                await read_paths(keys)
                keys.clear()
        if keys:
            await read_paths(keys)
    return paths


def _qkey(chat_id) -> str:
    return f"queue:{chat_id}"


def _nkey(chat_id) -> str:
    return f"now:{chat_id}"


async def add_to_queue(chat_id, track):
    count, _ = await edit_queue(
        music_state, _qkey(chat_id), "append", tag_tracks([track]), QUEUE_TTL
    )
    return count


async def add_many_to_queue(chat_id, tracks):
    await edit_queue(music_state, _qkey(chat_id), "append", tag_tracks(tracks), QUEUE_TTL)


async def get_queue(chat_id):
    return await read_queue(music_state, _qkey(chat_id))


async def get_now_playing(chat_id):
    return await music_state.get(_nkey(chat_id))


async def set_now_playing(chat_id, track):
    if track is None:
        await music_state.delete(_nkey(chat_id))
    else:
        await music_state.set(_nkey(chat_id), track, ttl=QUEUE_TTL)


async def pop_next(chat_id):
    _, track = await edit_queue(music_state, _qkey(chat_id), "pop", 1, QUEUE_TTL)
    return track


async def remove_from_queue(chat_id, queue_id):
    _, track = await edit_queue(music_state, _qkey(chat_id), "remove", queue_id, QUEUE_TTL)
    return track


async def update_queue_track(chat_id, queue_id, *, autoplay=False, **changes):
    key = _aqkey(chat_id) if autoplay else _qkey(chat_id)
    await edit_queue(music_state, key, "update", [{**changes, "_queue_id": queue_id}], QUEUE_TTL)


def _aqkey(chat_id) -> str:
    return f"autoplay_q:{chat_id}"


async def get_autoplay_queue(chat_id) -> list[dict]:
    return await read_queue(music_state, _aqkey(chat_id))


async def set_autoplay_queue(chat_id, tracks: list[dict]):
    await edit_queue(music_state, _aqkey(chat_id), "reset", tag_tracks(tracks), QUEUE_TTL)


async def pop_autoplay_next(chat_id) -> dict | None:
    _, track = await edit_queue(music_state, _aqkey(chat_id), "pop", 1, QUEUE_TTL)
    return track


async def clear_autoplay_queue(chat_id):
    await music_state.delete(_aqkey(chat_id))


async def clear_queue(chat_id):
    import orjson

    from Emilia.application import redis_client

    keys = (_qkey(chat_id), _nkey(chat_id), _aqkey(chat_id))
    pipe = redis_client.pipeline(transaction=True)
    pipe.delete(*(music_state._rkey(key) for key in keys))
    for key in keys:
        music_state._invalidate(key)
        pipe.publish(
            music_state._channel_name, orjson.dumps({"i": music_state._instance_id, "k": key})
        )
    try:
        await pipe.execute()
    finally:
        for key in keys:
            music_state._invalidate(key)


async def get_cached_media(video_id, is_video=False):
    return await music_cache.get(f"{video_id}_{is_video}")


async def set_cached_media(video_id, file_id, is_video=False):
    await music_cache.set(f"{video_id}_{is_video}", file_id, ttl=FILE_TTL)


async def get_cached_meta(norm):
    return await music_meta.get(norm)


async def set_cached_meta(norm, meta):
    await music_meta.set(norm, meta, ttl=META_TTL)


async def set_menu(chat_id, data):
    await music_menu.set(f"menu:{chat_id}", data, ttl=300)


async def get_menu(chat_id):
    return await music_menu.get(f"menu:{chat_id}")


async def clear_menu(chat_id):
    await music_menu.delete(f"menu:{chat_id}")


async def set_queue_direct(chat_id, queue_list):
    await edit_queue(music_state, _qkey(chat_id), "merge", queue_list, QUEUE_TTL)


async def set_playback_message_id(chat_id, message_id):
    await music_state.set(f"playback_msg:{chat_id}", message_id, ttl=QUEUE_TTL)


async def get_playback_message_id(chat_id):
    return await music_state.get(f"playback_msg:{chat_id}")


async def set_loop_mode(chat_id, mode: str):
    await music_state.set(f"loop:{chat_id}", mode, ttl=QUEUE_TTL * 4)


async def get_loop_mode(chat_id) -> str:
    val = await music_state.get(f"loop:{chat_id}")
    return val if val in ("off", "one", "all") else "off"


async def set_shuffle_mode(chat_id, enabled: bool):
    await music_state.set(f"shuffle:{chat_id}", bool(enabled), ttl=QUEUE_TTL * 4)


async def get_shuffle_mode(chat_id) -> bool:
    val = await music_state.get(f"shuffle:{chat_id}")
    return bool(val)


async def set_paused(chat_id, paused: bool):
    await music_state.set(f"paused:{chat_id}", paused, ttl=QUEUE_TTL)


async def get_paused(chat_id) -> bool:
    val = await music_state.get(f"paused:{chat_id}")
    return bool(val)
