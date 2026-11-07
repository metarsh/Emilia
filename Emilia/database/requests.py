# something my fans requested me to make :p

import re
import time
from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument

from Emilia.application import db
from Emilia.database.common import (
    atomic_find_one_and_update,
    atomic_upsert,
    next_sequence,
    save_named_entry,
)

requests_coll = db.requests
settings_coll = db.request_settings
limits_coll = db.request_limits


async def get_settings(chat_id: int) -> dict[str, Any]:
    return await settings_coll.find_one({"_id": chat_id}) or {}


async def update_settings(chat_id: int, updates: dict[str, Any]):
    return await atomic_upsert(settings_coll, {"_id": chat_id}, {"$set": updates})


async def add_channel(chat_id: int, ch_id: int, title: str, username: str | None = None) -> bool:
    channel_obj = {"id": ch_id, "title": title, "username": username}
    await save_named_entry(settings_coll, {"_id": chat_id}, "channels", "id", ch_id, channel_obj)
    return True


async def remove_channel(chat_id: int, ident: str | int) -> bool:
    clean = str(ident).lstrip("@").strip().lower()
    ch_id = (
        int(clean) if (clean.isdigit() or (clean.startswith("-") and clean[1:].isdigit())) else None
    )

    pull_query = [{"username": {"$regex": f"^{re.escape(clean)}$", "$options": "i"}}]
    if ch_id is not None:
        pull_query.append({"id": ch_id})

    res = await settings_coll.update_one(
        {"_id": chat_id},
        {"$pull": {"channels": {"$or": pull_query}}},
    )
    return res.modified_count > 0


async def set_req_limit(chat_id: int, limit: int):
    return await update_settings(chat_id, {"daily_limit": max(0, limit)})


async def get_req_limit(chat_id: int) -> int:
    doc = await settings_coll.find_one({"_id": chat_id}, {"_id": 0, "daily_limit": 1})
    return int((doc or {}).get("daily_limit", 0))


async def check_and_increment_daily_limit(
    chat_id: int, user_id: int, max_limit: int
) -> tuple[bool, int]:
    if max_limit <= 0:
        return True, 0

    now = datetime.now(UTC)
    today = now.strftime("%Y-%m-%d")
    limit_id = f"{chat_id}_{user_id}_{today}"

    count = {"$ifNull": ["$count", 0]}
    previous = await atomic_find_one_and_update(
        limits_coll,
        {"_id": limit_id},
        [
            {
                "$set": {
                    "count": {"$cond": [{"$lt": [count, max_limit]}, {"$add": [count, 1]}, count]},
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "date": today,
                    "created_at": {"$ifNull": ["$created_at", now]},
                }
            }
        ],
        return_document=ReturnDocument.BEFORE,
        projection={"_id": 0, "count": 1},
    )
    used = (previous or {}).get("count") or 0
    return (True, used + 1) if used < max_limit else (False, used)


async def create_request(
    chat_id: int,
    user_id: int,
    user_name: str,
    query: str,
    req_channel: int | None = None,
) -> dict[str, Any]:
    num = await next_sequence(db.counters, "req")
    doc = {
        "_id": f"req_{num}",
        "num": num,
        "user_id": user_id,
        "user_name": user_name,
        "query": query.strip(),
        "norm_query": query.strip().lower(),
        "chat_id": chat_id,
        "req_channel": req_channel,
        "status": "pending",
        "created_at": time.time(),
        "post_url": None,
        "reason": None,
    }
    stored = await atomic_find_one_and_update(
        requests_coll,
        {"chat_id": chat_id, "norm_query": doc["norm_query"], "status": "pending"},
        {"$setOnInsert": doc, "$addToSet": {"subscribers": user_id}},
        return_document=ReturnDocument.AFTER,
    )
    if stored["num"] != num:
        stored["_existing"] = True
    return stored


async def find_active_request(query: str, chat_id: int | None = None) -> dict[str, Any] | None:
    q: dict[str, Any] = {"norm_query": query.strip().lower(), "status": "pending"}
    if chat_id is not None:
        q["chat_id"] = chat_id
    return await requests_coll.find_one(q)


async def add_subscriber(req_id: str | int, user_id: int) -> bool:
    num = _request_number(req_id)
    res = await requests_coll.update_one({"num": num}, {"$addToSet": {"subscribers": user_id}})
    return res.modified_count > 0


async def update_request_status(
    req_id: str | int,
    status: str,
    post_url: str | None = None,
    reason: str | None = None,
) -> dict[str, Any] | None:
    if status not in {"completed", "rejected"}:
        raise ValueError("Request status must be completed or rejected")
    num = _request_number(req_id)
    return await requests_coll.find_one_and_update(
        {"num": num, "status": "pending"},
        {
            "$set": {
                "status": status,
                "post_url": post_url,
                "reason": reason,
                "updated_at": time.time(),
            }
        },
        return_document=ReturnDocument.AFTER,
    )


async def get_user_requests(user_id: int, limit: int = 8) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    return (
        await requests_coll.find({"subscribers": user_id})
        .sort("created_at", -1)
        .limit(limit)
        .to_list(length=limit)
    )


def _request_number(req_id: str | int) -> int:
    clean = str(req_id).lstrip("#").lower().removeprefix("req-").removeprefix("req_").strip()
    return int(clean)


async def get_request(req_id: str | int) -> dict[str, Any] | None:
    try:
        num = _request_number(req_id)
    except ValueError:
        return None
    return await requests_coll.find_one({"num": num})
