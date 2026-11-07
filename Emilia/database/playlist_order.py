# something you should not touch if you are inexperienced, it would break playlist completely if you do

import asyncio
from functools import wraps
from weakref import WeakValueDictionary

from pymongo import UpdateOne

from Emilia.services.mutations import mutation_claim

_LOCKS = WeakValueDictionary()


async def refresh_stats(playlists, songs, playlist_id):
    cursor = await songs.aggregate(
        [
            {"$match": {"playlist_id": playlist_id}},
            {"$group": {"_id": None, "count": {"$sum": 1}, "duration": {"$sum": "$duration"}}},
        ]
    )
    stats = await cursor.to_list(length=1)
    row = stats[0] if stats else {}
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {
            "$set": {"song_count": row.get("count", 0), "duration_total": row.get("duration", 0)},
            "$unset": {"songs_dirty": ""},
        },
    )


async def repair_order(playlists, songs, playlist_id, order=None):
    rows = (
        await songs.find({"playlist_id": playlist_id}, {"video_id": 1, "position": 1})
        .sort("position", 1)
        .limit(10001)
        .to_list(length=10001)
    )
    if len(rows) > 10000:
        raise ValueError("Playlist exceeds the supported ordering limit")
    if order is None:
        document = await playlists.find_one({"playlist_id": playlist_id}, {"pending_order": 1})
        order = (document or {}).get("pending_order")
    by_id = {row["video_id"]: row for row in rows}
    ordered = [by_id.pop(video_id) for video_id in (order or []) if video_id in by_id]
    ordered.extend(sorted(by_id.values(), key=lambda row: row["position"]))
    await playlists.update_one(
        {"playlist_id": playlist_id},
        {"$set": {"pending_order": [row["video_id"] for row in ordered], "songs_dirty": True}},
    )
    if ordered:
        # Each row has the same reserved negative slot on every recovery retry.
        await songs.bulk_write(
            [
                UpdateOne({"_id": row["_id"]}, {"$set": {"position": -position}})
                for position, row in enumerate(ordered, 1)
            ],
            ordered=False,
        )
        await songs.bulk_write(
            [
                UpdateOne({"_id": row["_id"]}, {"$set": {"position": position}})
                for position, row in enumerate(ordered, 1)
            ],
            ordered=False,
        )
    await playlists.update_one({"playlist_id": playlist_id}, {"$unset": {"pending_order": ""}})


def serialized(playlists, songs, *, repair=True, mark_dirty=True, allow_deleting=False):
    def decorate(function):
        @wraps(function)
        async def wrapped(playlist_id, *args, **kwargs):
            lock = _LOCKS.setdefault(playlist_id, asyncio.Lock())
            async with (
                lock,
                mutation_claim(playlists.database.playlist_mutations, f"playlist:{playlist_id}"),
            ):
                document = await playlists.find_one(
                    {"playlist_id": playlist_id},
                    {"_id": 0, "songs_dirty": 1, "pending_order": 1, "deleting": 1},
                )
                if document is None or (document.get("deleting") and not allow_deleting):
                    if mark_dirty:
                        raise ValueError("Playlist not found")
                    return await function(playlist_id, *args, **kwargs)
                if repair:
                    if document.get("songs_dirty") or document.get("pending_order") is not None:
                        await repair_order(playlists, songs, playlist_id)
                        await refresh_stats(playlists, songs, playlist_id)
                    if mark_dirty:
                        await playlists.update_one(
                            {"playlist_id": playlist_id}, {"$set": {"songs_dirty": True}}
                        )
                result = await function(playlist_id, *args, **kwargs)
                if repair and mark_dirty:
                    await refresh_stats(playlists, songs, playlist_id)
                return result

        return wrapped

    return decorate
