import asyncio
import math
import time

import orjson
from pymongo.errors import PyMongoError

from Emilia.application import LOGGER, redis_client
from Emilia.config import Config
from Emilia.database import playlists as db
from Emilia.locales import tr

MODE_GLYPH = {
    db.ACCESS_PRIVATE: "◌",
    db.ACCESS_UNLISTED: "◍",
    db.ACCESS_PUBLIC: "◯",
    db.ACCESS_SERVER: "▣",
    db.ACCESS_COLLAB: "◈",
}

MODE_LABEL = {
    db.ACCESS_PRIVATE: "Private",
    db.ACCESS_UNLISTED: "Unlisted",
    db.ACCESS_PUBLIC: "Public",
    db.ACCESS_SERVER: "Server",
    db.ACCESS_COLLAB: "Collaborative",
}


def can_view(playlist: dict, user_id: int, chat_id: int | None = None) -> bool:
    """Check if user can view this playlist."""
    if not playlist:
        return False
    if playlist.get("banned"):
        return False

    mode = playlist.get("access_mode")
    owner = playlist.get("owner_id")

    if mode == db.ACCESS_PUBLIC or mode == db.ACCESS_UNLISTED:
        return True
    if user_id == owner:
        return True
    if user_id in playlist.get("editors", []):
        return True
    if mode == db.ACCESS_SERVER and chat_id == playlist.get("server_chat_id"):
        return True
    return False


def can_edit(playlist: dict, user_id: int) -> bool:
    """Check if user can modify this playlist."""
    if not playlist or playlist.get("banned"):
        return False
    owner = playlist.get("owner_id")
    if user_id == owner:
        return True
    if user_id in playlist.get("editors", []):
        return True
    return False


async def check_duplicate(playlist_id: str, track: dict) -> tuple[bool, dict | None]:
    """
    Check if track already exists in playlist.
    """
    video_id = track.get("video_id") or track.get("id")
    if not video_id:
        return False, None
    existing = await db.find_song(playlist_id, video_id)
    return (existing is not None), existing


def compute_trending_score(pl: dict) -> float:
    """
    Trending Score = (plays + likes*2 + forks*3 + saves*1.5 + completion*10) * decay

    Decay: exponential with half-life of 7 days.
    Age is measured from updated_at (not created_at) so actively maintained
    playlists stay fresh.
    """
    if pl.get("song_count", 0) == 0:
        return 0.0

    plays = pl.get("plays", 0)
    likes = pl.get("likes", 0)
    saves = pl.get("saves", 0)
    forks = pl.get("forks", 0)
    completion_sum = pl.get("completion_sum", 0.0)
    completion_n = pl.get("completion_n", 0)

    completion_avg = (completion_sum / completion_n) if completion_n > 0 else 0.0

    engagement = plays + likes * 2 + forks * 3 + saves * 1.5 + completion_avg * 10

    now = time.time()
    updated_at = pl.get("updated_at", pl.get("created_at", now))
    age_days = (now - updated_at) / 86400.0

    # Half-life decay: after 7 days, score is cut in half
    half_life = 7.0
    decay = math.pow(0.5, age_days / half_life)

    return max(0.0, engagement * decay)


async def update_all_trending_scores(batch_size: int = 500):
    """
    Recalculate trending scores for all public playlists.
    Run as a background task every few hours.
    """
    LOGGER.info("[Playlists] Starting trending score update...")
    count = 0
    scores = {}

    async for pl in db.iter_rankable(batch=batch_size):
        score = compute_trending_score(pl)
        scores[pl["playlist_id"]] = score
        count += 1

        if len(scores) >= batch_size:
            await db.set_trending_scores(scores)
            scores.clear()

    if scores:
        await db.set_trending_scores(scores)

    LOGGER.info(f"[Playlists] Updated trending scores for {count} playlists.")


async def add_song_with_prompt(
    playlist_id: str, track: dict, added_by: int
) -> tuple[str, int, dict | None]:
    """
    Add a song, detecting duplicates.
    """
    video_id = track.get("video_id") or track.get("id")
    if not video_id:
        return "invalid", 0, None

    is_dup, existing = await check_duplicate(playlist_id, track)
    if is_dup:
        return "duplicate", 0, existing

    status, pos = await db.add_song(playlist_id, track, added_by)
    if status == "added":
        # Log activity
        await db.log_activity(
            playlist_id,
            added_by,
            "added_song",
            {"title": track.get("title"), "video_id": video_id},
        )
    return status, pos, None


async def replace_duplicate(playlist_id: str, video_id: str, track: dict, user_id: int) -> bool:
    """Replace existing song metadata."""
    success = await db.replace_song(playlist_id, video_id, track, user_id)
    if success:
        await db.log_activity(
            playlist_id,
            user_id,
            "replaced_song",
            {"title": track.get("title"), "video_id": video_id},
        )
    return success


async def import_tracks_bulk(playlist_id: str, tracks: list[dict], user_id: int) -> tuple[int, int]:
    """
    Import many tracks at once (from Spotify/YouTube playlist)
    """
    if not tracks:
        return 0, 0

    added, skipped = await db.add_songs_bulk(playlist_id, tracks, user_id)
    if added > 0:
        await db.log_activity(playlist_id, user_id, "bulk_import", {"count": added})
    return added, skipped


async def fork_playlist(source_id: str, user_id: int, new_title: str | None = None) -> str | None:
    """
    Fork a playlist (copy all songs and metadata)
    """
    source = await db.get_playlist(source_id)
    if not source:
        return None
    songs = await db.get_songs(source_id)

    title = new_title or f"{source['title']} (fork)"
    fork_root = source.get("fork_root") or source_id
    fork_gen = source.get("fork_generation", 0) + 1

    new_pl = await db.create_playlist(
        owner_id=user_id,
        title=title,
        access_mode=db.ACCESS_PRIVATE,
        description=tr("playlist.forked_from", title=source["title"]),
        forked_from=source_id,
        fork_generation=fork_gen,
        fork_root=fork_root,
    )
    if not new_pl:
        return None

    new_id = new_pl["playlist_id"]

    try:
        if songs:
            await db.add_songs_bulk(new_id, songs, user_id)
    except (Exception, asyncio.CancelledError):
        from Emilia.utils.tasks import finish_cleanup

        await finish_cleanup(db.delete_playlist(new_id))
        raise
    try:
        await db.log_activity(source_id, user_id, "forked", {"new_id": new_id})
    except ValueError:
        # A copied fork remains usable if the source was deleted in the meantime.
        pass

    return new_id


async def get_trending(limit: int = 20, skip: int = 0) -> list[dict]:
    """Get trending public playlists."""
    return await db.get_trending(limit=limit, skip=skip)


_SESSION_TTL = 6 * 3600  # a voice chat that has been idle this long is over

_TRACK_FINISHED = """
local raw = redis.call('GET', KEYS[1])
if not raw then return 0 end
local state = cjson.decode(raw)
state['played'] = (state['played'] or 0) + 1
redis.call('SET', KEYS[1], cjson.encode(state), 'EX', ARGV[1])
return state['played']
"""


def _session_key(chat_id: int) -> str:
    return f"{Config.CACHE_NAMESPACE}:music:{Config.BOT_ID}:pl_session:{chat_id}"


async def session_start(chat_id: int, playlist_id: str, user_id: int, total: int) -> None:
    await redis_client.set(
        _session_key(chat_id),
        orjson.dumps(
            {"pid": playlist_id, "user": user_id, "total": max(total, 1), "played": 0}
        ).decode(),
        ex=_SESSION_TTL,
    )


async def session_track_finished(chat_id: int) -> None:
    await redis_client.register_script(_TRACK_FINISHED)(
        keys=[_session_key(chat_id)], args=[_SESSION_TTL]
    )


_ACTIVE_GROUP_TTL = 6 * 3600


def _active_group_key(user_id: int) -> str:
    return f"{Config.CACHE_NAMESPACE}:music:{Config.BOT_ID}:pl_group:{user_id}"


async def remember_group(user_id: int, chat_id: int) -> None:
    if chat_id >= 0:  # PM ids are positive; there is nothing to remember
        return
    await redis_client.set(_active_group_key(user_id), str(chat_id), ex=_ACTIVE_GROUP_TTL)


async def recall_group(user_id: int) -> int | None:
    raw = await redis_client.get(_active_group_key(user_id))
    if not raw:
        return None
    if isinstance(raw, bytes):
        raw = raw.decode()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


async def session_finish(chat_id: int) -> None:
    raw = await redis_client.getdel(_session_key(chat_id))
    if not raw:
        return
    state = orjson.loads(raw)
    completion = min(1.0, state["played"] / state["total"])
    await db.record_play(state["pid"], state["user"], completion)


async def start_trending_refresh_task(interval: int = 3600 * 4):
    """
    Periodically recalculate trending scores
    """
    while True:
        await asyncio.sleep(interval)
        try:
            await update_all_trending_scores()
        except PyMongoError as e:
            LOGGER.error(f"[Playlists] Trending refresh failed: {e}")


def format_duration(seconds: int) -> str:
    """Format duration as H:MM:SS or M:SS."""
    if seconds <= 0:
        return "0:00"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


_BAR_FILLED = "▰"
_BAR_EMPTY = "▱"


def render_bar(value: float, maximum: float, width: int = 10) -> str:
    if maximum <= 0:
        return _BAR_EMPTY * width
    filled = int(round(min(1.0, value / maximum) * width))
    return _BAR_FILLED * filled + _BAR_EMPTY * (width - filled)


def build_playlist_caption(pl: dict) -> str:
    title = pl.get("title", "Untitled")
    desc = pl.get("description", "")
    count = pl.get("song_count", 0)
    duration = format_duration(pl.get("duration_total", 0))

    mode = pl.get("access_mode", "private")
    mode_label = MODE_LABEL.get(mode, "Private")

    lines = [
        f"**{title}**",
        f"`•` **Songs:** {count}",
        f"`•` **Duration:** {duration}",
        f"`•` **Access:** {MODE_GLYPH.get(mode, '')} {mode_label}",
    ]

    if desc:
        lines.append(f"`•` **Description:** {desc}")

    plays = pl.get("plays", 0)
    likes = pl.get("likes", 0)
    saves = pl.get("saves", 0)
    forks = pl.get("forks", 0)
    if any([plays, likes, saves, forks]):
        lines.append(
            tr(
                "playlist.stats_plays_likes_saves_forks",
                plays=plays,
                likes=likes,
                saves=saves,
                forks=forks,
            )
        )

    forked_from = pl.get("forked_from")
    if forked_from:
        gen = pl.get("fork_generation", 1)
        lines.append(tr("playlist.forked_from_gen", forked_from=forked_from, gen=gen))

    return "\n".join(lines)
