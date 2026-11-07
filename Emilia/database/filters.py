# filters help you get automated replies through keywords/phrases mentioned

from pymongo import ReturnDocument

from Emilia.application import db
from Emilia.database.common import atomic_find_one_and_update, named_array_update

filters = db.filters
MAX_FILTERS = 69


async def add_filter_db(
    chat_id: int,
    filter_name: str,
    content: str | None,
    text: str | dict | None,
    data_type: int,
    reply_to_sender: bool = False,
) -> bool:
    entry = {
        "filter_name": filter_name,
        "content": content,
        "text": text,
        "data_type": data_type,
        "reply_to_sender": reply_to_sender,
    }
    update = named_array_update(
        "filters", "filter_name", filter_name, entry, max_entries=MAX_FILTERS
    )
    doc = await atomic_find_one_and_update(
        filters,
        {"chat_id": chat_id},
        update,
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "filters": {"$elemMatch": {"filter_name": filter_name}}},
    )
    return bool(doc.get("filters"))


async def stop_db(chat_id: int, filter_name: str):
    await filters.update_one(
        {"chat_id": chat_id}, {"$pull": {"filters": {"filter_name": filter_name}}}
    )


async def stop_all_db(chat_id: int):
    await filters.update_one({"chat_id": chat_id}, {"$set": {"filters": []}})


async def get_filter(chat_id: int, filter_name: str):
    doc = await filters.find_one(
        {"chat_id": chat_id},
        {"_id": 0, "filters": {"$elemMatch": {"filter_name": filter_name}}},
    )
    if doc and doc.get("filters"):
        f = doc["filters"][0]
        return (
            f.get("filter_name"),
            f.get("content"),
            f.get("text"),
            f.get("data_type"),
            f.get("reply_to_sender", False),
        )


async def get_filters_list(chat_id: int):
    doc = await filters.find_one({"chat_id": chat_id}, {"_id": 0, "filters.filter_name": 1})
    if doc and doc.get("filters"):
        return [f.get("filter_name") for f in doc["filters"] if f.get("filter_name")]
    else:
        return []
