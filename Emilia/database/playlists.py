# playlists, songs.

import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument, UpdateOne
from pymongo.errors import BulkWriteError, DuplicateKeyError

from Emilia.application import db
from Emilia.config import Config
from Emilia.database.playlist_order import serialized
from Emilia.locales import tr
from Emilia.services.mutations import mutation_claim
from Emilia.utils.tasks import finish_cleanup

playlists = db.playlists
playlist_songs = db.playlist_songs
playlist_likes = db.playlist_likes
playlist_activity = db.playlist_activity
playlist_reports = db.playlist_reports
playlist_plays = db.playlist_plays


ACCESS_PRIVATE = "private"
ACCESS_UNLISTED = "unlisted"
ACCESS_PUBLIC = "public"
ACCESS_SERVER = "server"
ACCESS_COLLAB = "collab"

ACCESS_MODES = (
    ACCESS_PRIVATE,
    ACCESS_UNLISTED,
    ACCESS_PUBLIC,
    ACCESS_SERVER,
    ACCESS_COLLAB,
)

DISCOVERABLE_MODES = (ACCESS_PUBLIC,)

LIKED_SONGS_TITLE = tr("playlists.liked_songs")

MAX_SONGS_PER_PLAYLIST = Config.PLAYLIST_MAX_SONGS
MAX_PLAYLISTS_PER_USER = Config.PLAYLIST_MAX_PER_USER
ACTIVITY_KEEP = 100

# Short, URL-safe, unambiguous. Excludes look-alikes (0/O, 1/l/I) so a playlist
# id read off a QR code or dictated aloud round-trips.
_ID_ALPHABET = "23456789abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ"
_ID_LEN = 10


def _new_playlist_id() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(_ID_LEN))


def _now() -> float:
    return time.time()


def _page(skip, limit, maximum=100):
    return max(0, int(skip)), max(1, min(int(limit), maximum))


def _playlist_doc(
    owner_id,
    title,
    access_mode=ACCESS_PRIVATE,
    description="",
    server_chat_id=None,
    forked_from=None,
    fork_generation=0,
    fork_root=None,
):
    now = _now()
    return {
        "playlist_id": _new_playlist_id(),
        "owner_id": owner_id,
        "title": title,
        "description": description,
        "access_mode": access_mode,
        "server_chat_id": server_chat_id,
        "editors": [],
        "created_at": now,
        "updated_at": now,
        "song_count": 0,
        "duration_total": 0,
        "thumbnail": None,
        "plays": 0,
        "likes": 0,
        "saves": 0,
        "forks": 0,
        "completion_sum": 0.0,
        "completion_n": 0,
        "trending_score": 0.0,
        "scored_at": 0.0,
        "forked_from": forked_from,
        "fork_generation": fork_generation,
        "fork_root": fork_root,
        "banned": False,
    }


async def create_playlist(owner_id, *args, **kwargs):
    async with mutation_claim(db.playlist_mutations, f"owner:{owner_id}"):
        source_id = kwargs.get("forked_from")
        if source_id:
            async with mutation_claim(db.playlist_mutations, f"playlist:{source_id}"):
                if not await playlists.find_one(
                    {"playlist_id": source_id, "deleting": {"$ne": True}}, {"_id": 1}
                ):
                    return None
                await playlists.update_one(
                    {"playlist_id": source_id}, {"$set": {"forks_dirty": True}}
                )
                result = await _create_playlist(owner_id, *args, **kwargs)
                await _refresh_forks(source_id)
                return result
        return await _create_playlist(owner_id, *args, **kwargs)


async def _create_playlist(
    owner_id: int,
    title: str,
    access_mode: str = ACCESS_PRIVATE,
    description: str = "",
    server_chat_id: int | None = None,
    forked_from: str | None = None,
    fork_generation: int = 0,
    fork_root: str | None = None,
) -> dict[str, Any] | None:
    if access_mode not in ACCESS_MODES:
        access_mode = ACCESS_PRIVATE

    owned = await playlists.count_documents({"owner_id": owner_id, "is_liked": {"$ne": True}})
    if owned >= MAX_PLAYLISTS_PER_USER:
        return None

    for _ in range(5):
        doc = _playlist_doc(
            owner_id,
            title,
            access_mode,
            description,
            server_chat_id,
            forked_from,
            fork_generation,
            fork_root,
        )
        try:
            await playlists.insert_one(doc)
            doc.pop("_id", None)
            return doc
        except DuplicateKeyError:
            if await playlists.find_one({"playlist_id": doc["playlist_id"]}, {"_id": 1}) is None:
                raise
    return None


async def get_playlist(playlist_id: str) -> dict[str, Any] | None:
    selector = {"playlist_id": playlist_id, "deleting": {"$ne": True}}
    document = await playlists.find_one(selector, {"_id": 0})
    if document and (
        any(
            document.get(key)
            for key in ("songs_dirty", "edges_dirty", "plays_dirty", "forks_dirty")
        )
        or "pending_order" in document
    ):
        await _recover_playlist(playlist_id)
        document = await playlists.find_one(selector, {"_id": 0})
    return document


async def get_playlists_bulk(playlist_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch many playlists at once."""
    if not playlist_ids:
        return {}
    cursor = playlists.find(
        {"playlist_id": {"$in": playlist_ids}, "deleting": {"$ne": True}}, {"_id": 0}
    )
    return {d["playlist_id"]: d async for d in cursor}


@serialized(playlists, playlist_songs, repair=False)
async def update_playlist(playlist_id: str, updates: dict[str, Any]) -> None:
    updates = dict(updates)
    updates["updated_at"] = _now()
    await playlists.update_one({"playlist_id": playlist_id}, {"$set": updates})


@serialized(playlists, playlist_songs, repair=False, mark_dirty=False, allow_deleting=True)
async def delete_playlist(playlist_id: str) -> None:
    await playlists.update_one({"playlist_id": playlist_id}, {"$set": {"deleting": True}})

    async def cleanup():
        document = await playlists.find_one({"playlist_id": playlist_id}, {"forked_from": 1})
        source_id = (document or {}).get("forked_from")
        if source_id:
            await playlists.update_one({"playlist_id": source_id}, {"$set": {"forks_dirty": True}})
        for collection in (
            playlist_songs,
            playlist_activity,
            playlist_likes,
            playlist_plays,
            playlist_reports,
        ):
            await collection.delete_many({"playlist_id": playlist_id})
        await playlists.delete_one({"playlist_id": playlist_id})
        if source_id:
            async with mutation_claim(db.playlist_mutations, f"playlist:{source_id}"):
                await _refresh_forks(source_id)

    await finish_cleanup(cleanup())


async def count_user_playlists(user_id: int) -> int:
    return await playlists.count_documents({"owner_id": user_id, "deleting": {"$ne": True}})


async def get_user_playlists(
    user_id: int,
    include_editable: bool = True,
    skip: int = 0,
    limit: int = MAX_PLAYLISTS_PER_USER,
) -> list[dict[str, Any]]:
    """Playlists the user owns, plus ones they can edit as a collaborator."""
    if include_editable:
        query = {"$or": [{"owner_id": user_id}, {"editors": user_id}]}
    else:
        query = {"owner_id": user_id}
    query["deleting"] = {"$ne": True}
    skip, limit = _page(skip, limit, MAX_PLAYLISTS_PER_USER)
    cursor = (
        playlists.find(query, {"_id": 0})
        .sort([("updated_at", -1), ("playlist_id", 1)])
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_server_playlists(
    chat_id: int, skip: int = 0, limit: int = 50
) -> list[dict[str, Any]]:
    skip, limit = _page(skip, limit)
    cursor = (
        playlists.find(
            {
                "access_mode": ACCESS_SERVER,
                "server_chat_id": chat_id,
                "banned": False,
                "deleting": {"$ne": True},
            },
            {"_id": 0},
        )
        .sort([("updated_at", -1), ("playlist_id", 1)])
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_or_create_liked_playlist(owner_id: int) -> dict[str, Any] | None:
    async with mutation_claim(db.playlist_mutations, f"owner:{owner_id}"):
        return await _get_or_create_liked_playlist(owner_id)


async def _get_or_create_liked_playlist(owner_id: int) -> dict[str, Any] | None:
    existing = await playlists.find_one({"owner_id": owner_id, "is_liked": True}, {"_id": 0})
    if existing:
        if not existing.get("deleting"):
            return existing
        await delete_playlist(existing["playlist_id"])

    for _ in range(5):
        doc = _playlist_doc(
            owner_id, LIKED_SONGS_TITLE, description=tr("playlists.tracks_saved_button")
        )
        doc["is_liked"] = True
        try:
            return await playlists.find_one_and_update(
                {"owner_id": owner_id, "is_liked": True},
                {"$setOnInsert": doc},
                upsert=True,
                return_document=ReturnDocument.AFTER,
                projection={"_id": 0},
            )
        except DuplicateKeyError:
            existing = await playlists.find_one(
                {"owner_id": owner_id, "is_liked": True}, {"_id": 0}
            )
            if existing is not None:
                return existing
            if await playlists.find_one({"playlist_id": doc["playlist_id"]}, {"_id": 1}) is None:
                raise
    return None


def _song_doc(
    playlist_id: str, position: int, track: dict[str, Any], added_by: int
) -> dict[str, Any]:
    return {
        "playlist_id": playlist_id,
        "video_id": track.get("video_id") or track.get("id"),
        "position": position,
        "added_at": _now(),
        "added_by": added_by,
        # Cached track metadata
        "title": track.get("title") or "Unknown",
        "duration": int(track.get("duration") or 0),
        "thumbnail": track.get("thumbnail"),
        "uploader": track.get("uploader"),
        "webpage_url": track.get("webpage_url"),
        "source": track.get("source", "youtube"),
    }


async def find_song(playlist_id: str, video_id: str) -> dict[str, Any] | None:
    return await playlist_songs.find_one(
        {"playlist_id": playlist_id, "video_id": video_id}, {"_id": 0}
    )


@serialized(playlists, playlist_songs)
async def add_song(playlist_id: str, track: dict[str, Any], added_by: int) -> tuple[str, int]:
    return await _insert_song(playlist_id, track, added_by)


async def _insert_song(playlist_id, track, added_by):
    video_id = track.get("video_id") or track.get("id")
    if not video_id:
        return "invalid", 0

    pl = await playlists.find_one({"playlist_id": playlist_id}, {"song_count": 1, "_id": 0})
    if pl and pl.get("song_count", 0) >= MAX_SONGS_PER_PLAYLIST:
        return "full", 0

    last = await playlist_songs.find_one(
        {"playlist_id": playlist_id}, {"position": 1}, sort=[("position", -1)]
    )
    position = (last["position"] + 1) if last else 1

    try:
        await playlist_songs.insert_one(_song_doc(playlist_id, position, track, added_by))
    except DuplicateKeyError:
        if (
            await playlist_songs.find_one(
                {"playlist_id": playlist_id, "video_id": video_id}, {"_id": 1}
            )
            is None
        ):
            raise
        return "duplicate", 0

    await _touch_playlist(playlist_id, track.get("thumbnail"))
    return "added", position


@serialized(playlists, playlist_songs)
async def toggle_song(playlist_id: str, track: dict[str, Any], added_by: int) -> tuple[str, int]:
    video_id = track.get("video_id") or track.get("id")
    removed = await _remove_song(playlist_id, {"video_id": video_id}) if video_id else None
    if removed:
        return "removed", 0
    return await _insert_song(playlist_id, track, added_by)


@serialized(playlists, playlist_songs)
async def add_songs_bulk(
    playlist_id: str, tracks: list[dict[str, Any]], added_by: int
) -> tuple[int, int]:
    if not tracks:
        return 0, 0

    pl = await playlists.find_one({"playlist_id": playlist_id}, {"song_count": 1, "_id": 0})
    current = pl.get("song_count", 0) if pl else 0
    room = max(0, MAX_SONGS_PER_PLAYLIST - current)
    if room == 0:
        return 0, len(tracks)

    existing_ids = set()
    position = 1
    cursor = playlist_songs.find(
        {"playlist_id": playlist_id}, {"video_id": 1, "position": 1, "_id": 0}
    )
    async for row in cursor:
        existing_ids.add(row.get("video_id"))
        position = max(position, row["position"] + 1)

    docs, skipped = [], 0
    for track in tracks:
        video_id = track.get("video_id") or track.get("id")
        if not video_id or video_id in existing_ids or len(docs) >= room:
            skipped += 1
            continue
        existing_ids.add(video_id)
        docs.append(_song_doc(playlist_id, position, track, added_by))
        position += 1

    if not docs:
        return 0, skipped

    try:
        await playlist_songs.insert_many(docs, ordered=False)
    except BulkWriteError as exc:
        if exc.details.get("writeConcernErrors") or any(
            error.get("code") != 11000 for error in exc.details.get("writeErrors", [])
        ):
            raise
        inserted = int(exc.details.get("nInserted", 0))
    else:
        inserted = len(docs)

    await _touch_playlist(playlist_id, docs[0].get("thumbnail"))
    return inserted, skipped + len(docs) - inserted


@serialized(playlists, playlist_songs)
async def replace_song(
    playlist_id: str, video_id: str, track: dict[str, Any], added_by: int
) -> bool:
    fields = {
        field: {"$literal": track[field]} if track.get(field) else {"$ifNull": [f"${field}", None]}
        for field in ("title", "thumbnail", "uploader", "webpage_url")
    }
    fields.update(
        {"duration": int(track.get("duration") or 0), "added_at": _now(), "added_by": added_by}
    )
    result = await playlist_songs.update_one(
        {"playlist_id": playlist_id, "video_id": video_id},
        [{"$set": fields}],
    )
    if result.matched_count:
        await _touch_playlist(playlist_id)
    return bool(result.matched_count)


@serialized(playlists, playlist_songs, mark_dirty=False)
async def get_songs(
    playlist_id: str, skip: int = 0, limit: int = MAX_SONGS_PER_PLAYLIST
) -> list[dict[str, Any]]:
    if not await playlists.find_one(
        {"playlist_id": playlist_id, "deleting": {"$ne": True}}, {"_id": 1}
    ):
        return []
    skip, limit = _page(skip, limit, MAX_SONGS_PER_PLAYLIST)
    cursor = (
        playlist_songs.find({"playlist_id": playlist_id}, {"_id": 0})
        .sort("position", 1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


@serialized(playlists, playlist_songs)
async def remove_song(playlist_id: str, position: int) -> dict[str, Any] | None:
    return await _remove_song(playlist_id, {"position": position})


async def _remove_song(playlist_id, selector):
    from Emilia.database.playlist_order import repair_order

    song = await playlist_songs.find_one_and_delete({"playlist_id": playlist_id, **selector})
    if song:
        await repair_order(playlists, playlist_songs, playlist_id)
        await playlists.update_one({"playlist_id": playlist_id}, {"$set": {"updated_at": _now()}})
    return song


@serialized(playlists, playlist_songs)
async def move_song(playlist_id: str, frm: int, to: int) -> bool:
    from Emilia.database.playlist_order import repair_order

    if frm == to:
        return True
    rows = (
        await playlist_songs.find({"playlist_id": playlist_id}, {"video_id": 1})
        .sort("position", 1)
        .limit(MAX_SONGS_PER_PLAYLIST + 1)
        .to_list(length=MAX_SONGS_PER_PLAYLIST + 1)
    )
    if not 1 <= frm <= len(rows) or not 1 <= to <= len(rows):
        return False
    order = [row["video_id"] for row in rows]
    order.insert(to - 1, order.pop(frm - 1))
    await repair_order(playlists, playlist_songs, playlist_id, order)
    await playlists.update_one({"playlist_id": playlist_id}, {"$set": {"updated_at": _now()}})
    return True


@serialized(playlists, playlist_songs)
async def clear_songs(playlist_id: str) -> None:
    await playlist_songs.delete_many({"playlist_id": playlist_id})
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {"$set": {"updated_at": _now()}},
    )


async def _touch_playlist(playlist_id: str, thumbnail: str | None = None) -> None:
    fields = {"updated_at": _now()}
    if thumbnail:
        fields["thumbnail"] = {"$ifNull": ["$thumbnail", {"$literal": thumbnail}]}
    await playlists.update_one({"playlist_id": playlist_id}, [{"$set": fields}])


async def add_editor(playlist_id: str, user_id: int) -> None:
    await playlists.update_one(
        {"playlist_id": playlist_id, "deleting": {"$ne": True}},
        {"$addToSet": {"editors": user_id}, "$set": {"updated_at": _now()}},
    )


async def remove_editor(playlist_id: str, user_id: int) -> None:
    await playlists.update_one(
        {"playlist_id": playlist_id, "deleting": {"$ne": True}},
        {"$pull": {"editors": user_id}, "$set": {"updated_at": _now()}},
    )


@serialized(playlists, playlist_songs, repair=False, mark_dirty=False)
async def _toggle_edge(playlist_id: str, user_id: int, kind: str) -> bool:
    if not await playlists.find_one(
        {"playlist_id": playlist_id, "deleting": {"$ne": True}}, {"_id": 1}
    ):
        return False
    await playlists.update_one({"playlist_id": playlist_id}, {"$set": {"edges_dirty": True}})
    selector = {"playlist_id": playlist_id, "user_id": user_id, "kind": kind}
    removed = await playlist_likes.find_one_and_delete(selector)
    if removed is None:
        try:
            await playlist_likes.insert_one({**selector, "created_at": _now()})
        except DuplicateKeyError:
            pass
    await _refresh_edges(playlist_id)
    return removed is None


async def toggle_like(playlist_id: str, user_id: int) -> bool:
    return await _toggle_edge(playlist_id, user_id, "like")


async def toggle_save(playlist_id: str, user_id: int) -> bool:
    return await _toggle_edge(playlist_id, user_id, "save")


async def _refresh_edges(playlist_id):
    cursor = await playlist_likes.aggregate(
        [
            {"$match": {"playlist_id": playlist_id}},
            {"$group": {"_id": "$kind", "count": {"$sum": 1}}},
        ]
    )
    counts = {row["_id"]: row["count"] async for row in cursor}
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {
            "$set": {"likes": counts.get("like", 0), "saves": counts.get("save", 0)},
            "$unset": {"edges_dirty": ""},
        },
    )


async def has_edge(playlist_id: str, user_id: int, kind: str) -> bool:
    return (
        await playlist_likes.find_one(
            {"playlist_id": playlist_id, "user_id": user_id, "kind": kind}, {"_id": 1}
        )
        is not None
    )


async def get_saved_playlists(user_id: int, skip: int = 0, limit: int = 50) -> list[dict[str, Any]]:
    skip, limit = _page(skip, limit)
    cursor = (
        playlist_likes.find({"user_id": user_id, "kind": "save"}, {"playlist_id": 1, "_id": 0})
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    ids = [row["playlist_id"] async for row in cursor]
    found = await get_playlists_bulk(ids)
    return [found[i] for i in ids if i in found]


@serialized(playlists, playlist_songs, repair=False)
async def record_play(playlist_id: str, user_id: int, completion: float) -> None:
    completion = max(0.0, min(1.0, float(completion)))
    await playlists.update_one({"playlist_id": playlist_id}, {"$set": {"plays_dirty": True}})
    await playlist_plays.insert_one(
        {
            "playlist_id": playlist_id,
            "user_id": user_id,
            "completion": completion,
            "created_at": _now(),
            "expires_at": datetime.now(UTC) + timedelta(days=30),
        }
    )
    await _refresh_plays(playlist_id)


async def _rolling_plays(playlist_ids):
    cursor = await playlist_plays.aggregate(
        [
            {
                "$match": {
                    "playlist_id": {"$in": playlist_ids},
                    "expires_at": {"$gt": datetime.now(UTC)},
                }
            },
            {
                "$group": {
                    "_id": "$playlist_id",
                    "plays": {"$sum": 1},
                    "completion_sum": {"$sum": "$completion"},
                    "completion_n": {"$sum": 1},
                }
            },
        ]
    )
    return {row.pop("_id"): row async for row in cursor}


async def _refresh_plays(playlist_id):
    counts = (await _rolling_plays([playlist_id])).get(
        playlist_id, {"plays": 0, "completion_sum": 0.0, "completion_n": 0}
    )
    await playlists.update_one(
        {"playlist_id": playlist_id}, {"$set": counts, "$unset": {"plays_dirty": ""}}
    )


@serialized(playlists, playlist_songs, repair=False)
async def log_activity(
    playlist_id: str, user_id: int, action: str, meta: dict[str, Any] | None = None
) -> None:
    await playlist_activity.insert_one(
        {
            "playlist_id": playlist_id,
            "user_id": user_id,
            "action": action,
            "meta": meta or {},
            "created_at": _now(),
        }
    )
    stale = (
        await playlist_activity.find({"playlist_id": playlist_id}, {"created_at": 1})
        .sort([("created_at", -1), ("_id", -1)])
        .skip(ACTIVITY_KEEP)
        .limit(1)
        .to_list(length=1)
    )
    if stale:
        boundary = stale[0]
        await playlist_activity.delete_many(
            {
                "playlist_id": playlist_id,
                "$or": [
                    {"created_at": {"$lt": boundary["created_at"]}},
                    {"created_at": boundary["created_at"], "_id": {"$lte": boundary["_id"]}},
                ],
            }
        )


async def get_activity(playlist_id: str, limit: int = 20) -> list[dict[str, Any]]:
    _, limit = _page(0, limit, ACTIVITY_KEEP)
    cursor = (
        playlist_activity.find({"playlist_id": playlist_id}, {"_id": 0})
        .sort([("created_at", -1), ("_id", -1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def _refresh_forks(source_id: str) -> None:
    count = await playlists.count_documents({"forked_from": source_id, "deleting": {"$ne": True}})
    await playlists.update_one(
        {"playlist_id": source_id}, {"$set": {"forks": count}, "$unset": {"forks_dirty": ""}}
    )


async def get_fork_children(playlist_id: str, limit: int = 50) -> list[dict[str, Any]]:
    _, limit = _page(0, limit)
    cursor = (
        playlists.find({"forked_from": playlist_id, "deleting": {"$ne": True}}, {"_id": 0})
        .sort([("created_at", -1), ("playlist_id", 1)])
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_fork_ancestors(playlist_id: str, max_depth: int = 20) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    max_depth = max(0, min(int(max_depth), 100))
    seen = {playlist_id}
    current = await get_playlist(playlist_id)
    while current and current.get("forked_from") and len(chain) < max_depth:
        parent_id = current["forked_from"]
        if parent_id in seen:  # defensive: never loop on corrupt lineage
            break
        seen.add(parent_id)
        parent = await get_playlist(parent_id)
        if not parent:
            chain.append({"playlist_id": parent_id, "title": None, "missing": True})
            break
        chain.append(parent)
        current = parent
    return chain


async def iter_rankable(batch: int = 500):
    batch = max(1, min(batch, 1000))
    cursor = playlists.find(
        {
            "access_mode": {"$in": list(DISCOVERABLE_MODES)},
            "banned": False,
            "deleting": {"$ne": True},
        },
        {
            "_id": 0,
            "playlist_id": 1,
            "song_count": 1,
            "plays": 1,
            "likes": 1,
            "saves": 1,
            "forks": 1,
            "completion_sum": 1,
            "completion_n": 1,
            "created_at": 1,
            "updated_at": 1,
        },
    ).batch_size(batch)

    async def with_plays(rows):
        counts = await _rolling_plays([row["playlist_id"] for row in rows])
        for row in rows:
            row.update(
                counts.get(
                    row["playlist_id"], {"plays": 0, "completion_sum": 0.0, "completion_n": 0}
                )
            )
        return rows

    rows = []
    async for doc in cursor:
        rows.append(doc)
        if len(rows) == batch:
            for row in await with_plays(rows):
                yield row
            rows.clear()
    if rows:
        for row in await with_plays(rows):
            yield row


async def set_trending_scores(scores: dict[str, float]) -> None:
    if not scores:
        return
    now = _now()
    ops = [
        UpdateOne(
            {"playlist_id": pid, "deleting": {"$ne": True}},
            {"$set": {"trending_score": score, "scored_at": now}},
        )
        for pid, score in scores.items()
    ]
    for chunk_start in range(0, len(ops), 500):
        await playlists.bulk_write(ops[chunk_start : chunk_start + 500], ordered=False)


async def get_trending(limit: int = 20, skip: int = 0) -> list[dict[str, Any]]:
    skip, limit = _page(skip, limit)
    cursor = (
        playlists.find(
            {
                "access_mode": ACCESS_PUBLIC,
                "banned": False,
                "song_count": {"$gt": 0},
                "deleting": {"$ne": True},
            },
            {"_id": 0},
        )
        .sort([("trending_score", -1), ("playlist_id", 1)])
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_recent(limit: int = 20, skip: int = 0) -> list[dict[str, Any]]:
    skip, limit = _page(skip, limit)
    cursor = (
        playlists.find(
            {
                "access_mode": ACCESS_PUBLIC,
                "banned": False,
                "song_count": {"$gt": 0},
                "deleting": {"$ne": True},
            },
            {"_id": 0},
        )
        .sort([("updated_at", -1), ("playlist_id", 1)])
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def search(query: str, limit: int = 20, skip: int = 0) -> list[dict[str, Any]]:
    query = query.strip()
    if not query:
        return []
    skip, limit = _page(skip, limit)
    cursor = (
        playlists.find(
            {
                "$text": {"$search": query},
                "access_mode": ACCESS_PUBLIC,
                "banned": False,
                "deleting": {"$ne": True},
            },
            {"_id": 0, "score": {"$meta": "textScore"}},
        )
        .sort([("score", {"$meta": "textScore"}), ("trending_score", -1), ("playlist_id", 1)])
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


@serialized(playlists, playlist_songs, repair=False)
async def report_playlist(playlist_id: str, reporter_id: int, reason: str) -> bool:
    try:
        await playlist_reports.insert_one(
            {
                "playlist_id": playlist_id,
                "reporter_id": reporter_id,
                "reason": reason[:500],
                "created_at": _now(),
                "resolved": False,
            }
        )
        return True
    except DuplicateKeyError:
        return False


async def get_open_reports(limit: int = 50) -> list[dict[str, Any]]:
    _, limit = _page(0, limit)
    cursor = (
        playlist_reports.find({"resolved": False}, {"_id": 0}).sort("created_at", -1).limit(limit)
    )
    return await cursor.to_list(length=limit)


async def resolve_reports(playlist_id: str) -> None:
    await playlist_reports.update_many({"playlist_id": playlist_id}, {"$set": {"resolved": True}})


async def set_banned(playlist_id: str, banned: bool) -> None:
    await playlists.update_one(
        {"playlist_id": playlist_id, "deleting": {"$ne": True}},
        {"$set": {"banned": banned, "updated_at": _now()}},
    )


@serialized(playlists, playlist_songs, mark_dirty=False)
async def _recover_playlist(playlist_id):
    document = await playlists.find_one(
        {"playlist_id": playlist_id, "deleting": {"$ne": True}},
        {"edges_dirty": 1, "plays_dirty": 1, "forks_dirty": 1},
    )
    if document and document.get("edges_dirty"):
        await _refresh_edges(playlist_id)
    if document and document.get("plays_dirty"):
        await _refresh_plays(playlist_id)
    if document and document.get("forks_dirty"):
        await _refresh_forks(playlist_id)


async def recover_mutations():
    from Emilia.application import LOGGER

    async for document in playlists.find(
        {
            "$or": [
                {"deleting": True},
                {"songs_dirty": True},
                {"edges_dirty": True},
                {"plays_dirty": True},
                {"forks_dirty": True},
                {"pending_order": {"$exists": True}},
            ]
        },
        {"playlist_id": 1, "deleting": 1},
    ):
        try:
            if document.get("deleting"):
                await delete_playlist(document["playlist_id"])
            else:
                await _recover_playlist(document["playlist_id"])
        except Exception:
            LOGGER.exception("Could not recover playlist mutation")
