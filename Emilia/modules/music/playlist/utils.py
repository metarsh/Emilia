import csv
import io
import json
import time

import segno

from Emilia.application import LOGGER
from Emilia.database import playlists as db
from Emilia.locales import tr
from Emilia.modules.music.playlist.core import format_duration
from Emilia.utils.client_context import bot_username

DEEPLINK_PREFIX = "pl"


def build_share_link(playlist_id: str) -> str:
    """t.me/<bot>?start=pl_<id>"""
    return f"https://t.me/{bot_username()}?start={DEEPLINK_PREFIX}_{playlist_id}"


def parse_deeplink(payload: str) -> str | None:
    """
    Extract a playlist id from a /start payload
    """
    if not payload:
        return None
    payload = payload.strip()
    if payload.startswith(f"{DEEPLINK_PREFIX}_"):
        payload = payload[len(DEEPLINK_PREFIX) + 1 :]
    return payload or None


async def resolve_shared_playlist(playlist_id: str, user_id: int) -> tuple[dict | None, str | None]:
    """
    Resolve a shared link to a playlist the recipient is allowed to open
    """
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return None, tr("playlist.playlist_link_invalid_playlist_deleted")
    if pl.get("banned"):
        return None, tr("playlist.playlist_has_removed_violating_rules")

    mode = pl.get("access_mode", db.ACCESS_PRIVATE)
    if mode in (db.ACCESS_PUBLIC, db.ACCESS_UNLISTED):
        return pl, None
    if user_id == pl.get("owner_id") or user_id in (pl.get("editors") or []):
        return pl, None
    if mode == db.ACCESS_SERVER:
        return None, tr("playlist.playlist_only_available_inside_its_own_group")
    return None, tr("playlist.playlist_private")


def generate_qr(playlist_id: str, title: str = "") -> io.BytesIO | None:
    """
    Render a share link as a PNG QR code
    """
    try:
        qr = segno.make(build_share_link(playlist_id), error="m")
        buf = io.BytesIO()
        qr.save(buf, kind="png", scale=8, border=3, dark="#000000", light="#ffffff")
        buf.seek(0)
        buf.name = f"playlist_{playlist_id}.png"
        return buf
    except (OSError, ValueError) as e:
        LOGGER.warning(f"[Playlists] QR generation failed for {playlist_id}: {e}")
        return None


EXPORT_FORMATS = ("json", "m3u", "csv")


def _export_json(pl: dict, songs: list[dict]) -> str:
    payload = {
        "playlist_id": pl.get("playlist_id"),
        "title": pl.get("title"),
        "description": pl.get("description") or "",
        "access_mode": pl.get("access_mode"),
        "owner_id": pl.get("owner_id"),
        "created_at": pl.get("created_at"),
        "exported_at": time.time(),
        "share_link": build_share_link(pl.get("playlist_id", "")),
        "track_count": len(songs),
        "tracks": [
            {
                "position": s.get("position"),
                "title": s.get("title"),
                "uploader": s.get("uploader"),
                "duration": s.get("duration"),
                "url": s.get("webpage_url"),
                "video_id": s.get("video_id"),
                "source": s.get("source"),
            }
            for s in songs
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _export_m3u(pl: dict, songs: list[dict]) -> str:
    """
    Extended M3U
    """
    lines = ["#EXTM3U", f"#PLAYLIST:{_flat(pl.get('title', 'Playlist'))}"]
    for s in songs:
        duration = int(s.get("duration") or -1)
        artist = _flat(s.get("uploader") or "")
        title = _flat(s.get("title") or "Unknown")
        label = f"{artist} - {title}" if artist else title
        lines.append(f"#EXTINF:{duration},{label}")
        lines.append(s.get("webpage_url") or "")
    return "\n".join(lines) + "\n"


def _export_csv(pl: dict, songs: list[dict]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["position", "title", "uploader", "duration", "url", "source"])
    for s in songs:
        writer.writerow(
            [
                s.get("position"),
                s.get("title") or "",
                s.get("uploader") or "",
                s.get("duration") or 0,
                s.get("webpage_url") or "",
                s.get("source") or "",
            ]
        )
    return buf.getvalue()


def _flat(text: str) -> str:
    return " ".join(str(text or "").split())


async def export_playlist(
    playlist_id: str, fmt: str = "json"
) -> tuple[io.BytesIO | None, str | None]:
    fmt = (fmt or "json").lower()
    if fmt not in EXPORT_FORMATS:
        return None, tr("playlist.unsupported_format_use", export_formats=", ".join(EXPORT_FORMATS))

    pl = await db.get_playlist(playlist_id)
    if not pl:
        return None, tr("playlist.commands.that_playlist_no_longer_exists")

    songs = await db.get_songs(playlist_id, limit=db.MAX_SONGS_PER_PLAYLIST)
    if not songs:
        return None, tr("playlist.playlist_empty_nothing_export")

    try:
        if fmt == "json":
            text = _export_json(pl, songs)
        elif fmt == "m3u":
            text = _export_m3u(pl, songs)
        else:
            text = _export_csv(pl, songs)
    except (TypeError, ValueError, csv.Error) as e:
        LOGGER.error(f"[Playlists] export {playlist_id} as {fmt} failed: {e}")
        return None, tr("playlist.export_failed")

    buf = io.BytesIO(text.encode("utf-8"))
    buf.name = f"{_safe_filename(pl.get('title', 'playlist'))}.{fmt}"
    buf.seek(0)
    return buf, None


def _safe_filename(title: str) -> str:
    cleaned = "".join(c if (c.isalnum() or c in " -_") else "_" for c in _flat(title)).strip()
    return (cleaned[:48] or "playlist").replace(" ", "_")


LIMIT_CREATE = (5, 300)  # new playlists: 5 per 5 min
LIMIT_IMPORT = (3, 600)
LIMIT_FORK = (10, 600)
LIMIT_REPORT = (5, 3600)
LIMIT_EXPORT = (5, 300)
LIMIT_QR = (10, 300)


async def guard_action(user_id: int, action: str, limit: tuple[int, int]) -> tuple[bool, int]:
    from Emilia.services.rate_limit import check_limit

    result = await check_limit(f"pl_limit:{action}:{user_id}", *limit, sliding=True)
    return result.allowed, max(1, round(result.retry_after)) if not result.allowed else 0


def limit_message(action: str, retry_after: int) -> str:
    return tr(
        "playlist.too_many_requests_try_again_about",
        action=action,
        retry_after=format_duration(retry_after),
    )


_SPAM_MARKERS = (
    "t.me/joinchat",
    "t.me/+",
    "bit.ly/",
    "tinyurl.com/",
    "chat.whatsapp.com",
    "porn",
    "xxx ",
    tr("playlist.free_money"),
    tr("playlist.click_here"),
)

_INVISIBLES = (
    "\u200b"  # Zero-width space
    "\u200c"  # Zero-width non-joiner
    "\u200d"  # Zero-width joiner
    "\u200e"  # Left-to-right mark
    "\u200f"  # Right-to-left mark
    "\u202a"  # Left-to-right embedding
    "\u202b"  # Right-to-left embedding
    "\u202c"  # Pop directional formatting
    "\u202d"  # Left-to-right override
    "\u202e"  # Right-to-left override
    "\ufeff"  # Zero-width no-break space (BOM)
)


def sanitize_text(text: str, max_len: int = 64) -> str:
    if not text:
        return ""
    cleaned = "".join(c for c in text if c not in _INVISIBLES)
    return " ".join(cleaned.split())[:max_len]


def is_spam(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    if any(marker in lowered for marker in _SPAM_MARKERS):
        return True
    # A name that is mostly URL is a promo slot, not a playlist title.
    if lowered.count("http") >= 2:
        return True
    return False


def validate_title(text: str) -> tuple[str | None, str | None]:
    clean = sanitize_text(text, max_len=64)
    if len(clean) < 1:
        return None, tr("playlist.title_empty")
    if is_spam(clean):
        return None, tr("playlist.title_looks_like_spam_pick_something_else")
    return clean, None
