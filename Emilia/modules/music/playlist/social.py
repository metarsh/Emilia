import time

from pymongo.errors import PyMongoError
from pyrogram.errors import RPCError

from Emilia.application import LOGGER, pgram
from Emilia.database import playlists as db
from Emilia.locales import tr
from Emilia.modules.music.playlist.core import format_duration, render_bar
from Emilia.utils.cache import SimpleCache

name_cache = SimpleCache(default_ttl=3600, namespace="pl_names")

MAX_LINEAGE_DEPTH = 10


async def resolve_name(user_id: int) -> str:
    key = str(user_id)
    cached = await name_cache.get(key)
    if cached:
        return cached

    name = f"User {user_id}"
    try:
        user = await pgram.get_users(user_id)
        if user:
            name = user.first_name or user.username or name
    except RPCError:
        # Deleted account, or never seen by this bot
        pass

    await name_cache.set(key, name)
    return name


async def resolve_names(user_ids: list[int]) -> dict[int, str]:
    unique = list({uid for uid in user_ids if uid})
    out = {}
    for uid in unique:
        out[uid] = await resolve_name(uid)
    return out


_ACTION_TEMPLATES = {
    "created": tr("playlist.social.created_playlist"),
    "added_song": tr("playlist.social.added"),
    "replaced_song": tr("playlist.social.replaced"),
    "removed_song": tr("playlist.social.removed"),
    "bulk_import": tr("playlist.social.imported_tracks"),
    "renamed": tr("playlist.social.renamed"),
    "described": tr("playlist.social.updated_description"),
    "access_changed": tr("playlist.social.set_access"),
    "editor_added": tr("playlist.social.added_editor"),
    "editor_removed": tr("playlist.social.removed_editor"),
    "forked": tr("playlist.social.forked_playlist"),
    "cleared": tr("playlist.social.cleared_every_song"),
    "moved_song": tr("playlist.social.reordered"),
}


def _relative_time(ts: float) -> str:
    """Compact age string: 3m, 5h, 2d."""
    delta = max(0, int(time.time() - ts))
    if delta < 60:
        return "now"
    if delta < 3600:
        return f"{delta // 60}m"
    if delta < 86400:
        return f"{delta // 3600}h"
    if delta < 86400 * 30:
        return f"{delta // 86400}d"
    return f"{delta // (86400 * 30)}mo"


def _describe(entry: dict) -> str:
    action = entry.get("action", "")
    meta = entry.get("meta") or {}
    template = _ACTION_TEMPLATES.get(action)
    if not template:
        return action.replace("_", " ") or tr("playlist.social.did_something")

    title = meta.get("title") or "a track"
    if len(title) > 40:
        title = title[:39] + "…"

    try:
        return template.format(
            title=title,
            count=meta.get("count", 0),
            mode=meta.get("mode", "private"),
            name=meta.get("name", "someone"),
        )
    except (KeyError, IndexError, TypeError, ValueError):
        return action.replace("_", " ")


async def render_activity_feed(playlist_id: str, limit: int = 20) -> str:
    entries = await db.get_activity(playlist_id, limit=limit)
    if not entries:
        return tr("playlist.social.activity_nothing_has_happened_here_yet")

    names = await resolve_names([e.get("user_id") for e in entries])

    lines = ["**◌ Activity**", ""]
    for e in entries:
        who = names.get(e.get("user_id"), "Someone")
        when = _relative_time(e.get("created_at", time.time()))
        lines.append(f"`{when:>4}` **{who}** {_describe(e)}")

    return "\n".join(lines)


async def render_lineage(playlist_id: str) -> str:
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return tr("playlist.social.lineage_playlist_not_found")

    lines = [tr("playlist.social.fork_lineage"), ""]

    ancestors = await db.get_fork_ancestors(playlist_id, max_depth=MAX_LINEAGE_DEPTH)
    if ancestors:
        # get_fork_ancestors walks upward; show it root-first so the tree reads
        # top-down like a git history.
        for depth, anc in enumerate(reversed(ancestors)):
            indent = "  " * depth
            # A missing ancestor is a real state: the parent was deleted after
            # this playlist forked from it. get_fork_ancestors marks those with
            # title=None rather than dropping them, so the chain stays honest.
            title = anc.get("title") or "_(deleted)_"
            lines.append(f"`{indent}├─` **{title}** `({anc['playlist_id']})`")
        indent = "  " * len(ancestors)
        lines.append(tr("playlist.social.here", indent=indent, title=pl.get("title", "Untitled")))
    else:
        lines.append(tr("playlist.social.original_not_fork", title=pl.get("title", "Untitled")))

    gen = pl.get("fork_generation", 0)
    if gen:
        lines.append("")
        lines.append(f"`•` **Generation:** {gen}")

    children = await db.get_fork_children(playlist_id, limit=10)
    lines.append("")
    if children:
        lines.append(tr("playlist.social.forks_playlist", forks=pl.get("forks", 0)))
        for c in children:
            lines.append(f"`  ↳` **{c.get('title', 'Untitled')}** — {c.get('song_count', 0)} songs")
        if pl.get("forks", 0) > len(children):
            lines.append(tr("playlist.social.more", forks=pl["forks"] - len(children)))
    else:
        lines.append(tr("playlist.social.no_one_has_forked_yet"))

    return "\n".join(lines)


async def render_stats(playlist_id: str) -> str:
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return tr("playlist.social.stats_playlist_not_found")

    plays = pl.get("plays", 0)
    likes = pl.get("likes", 0)
    saves = pl.get("saves", 0)
    forks = pl.get("forks", 0)
    songs = pl.get("song_count", 0)

    completion_n = pl.get("completion_n", 0)
    completion_avg = (pl.get("completion_sum", 0.0) / completion_n) if completion_n else 0.0

    created = pl.get("created_at", time.time())
    age_days = max(1, int((time.time() - created) / 86400))

    peak = max(plays, likes, saves, forks, 1)

    owner = await resolve_name(pl.get("owner_id", 0))

    lines = [
        f"**◫ Stats — {pl.get('title', 'Untitled')}**",
        "",
        f"`•` **Owner:** {owner}",
        tr("playlist.social.created_d_ago", age_days=age_days),
        f"`•` **Songs:** {songs} · {format_duration(pl.get('duration_total', 0))}",
        "",
        f"`▷ Plays ` `{render_bar(plays, peak)}` {plays}",
        f"`♡ Likes ` `{render_bar(likes, peak)}` {likes}",
        f"`⭳ Saves ` `{render_bar(saves, peak)}` {saves}",
        f"`⑂ Forks ` `{render_bar(forks, peak)}` {forks}",
        "",
        tr(
            "playlist.social.completion_rate",
            completion_avg=render_bar(completion_avg, 1.0),
            completion_avg_2=completion_avg * 100,
        )
        + (
            tr("playlist.social.from_sessions", completion_n=completion_n)
            if completion_n
            else tr("playlist.social.no_data")
        ),
        tr("playlist.social.trending_score", trending_score=pl.get("trending_score", 0)),
    ]

    if plays and age_days:
        lines.append(tr("playlist.social.plays_day", plays=plays / age_days))

    return "\n".join(lines)


async def log(playlist_id: str, user_id: int, action: str, **meta):
    try:
        await db.log_activity(playlist_id, user_id, action, meta or None)
    except PyMongoError as e:
        LOGGER.warning(f"[Playlists] activity log failed: {e}")
