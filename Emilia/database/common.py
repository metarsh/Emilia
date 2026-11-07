# helpers for documents containing named entries.

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


async def atomic_upsert(collection, selector, update, **options):
    try:
        return await collection.update_one(selector, update, upsert=True, **options)
    except DuplicateKeyError as exc:
        result = await collection.update_one(selector, update, **options)
        if not result.matched_count:
            raise exc
        return result


async def atomic_find_one_and_update(collection, selector, update, **options):
    try:
        return await collection.find_one_and_update(selector, update, upsert=True, **options)
    except DuplicateKeyError as exc:
        result = await collection.find_one_and_update(selector, update, **options)
        if result is None:
            raise exc
        return result


def named_array_update(array_field, identity_field, identity, entry, *, max_entries=None):
    existing = {"$ifNull": [f"${array_field}", []]}
    replacement = {
        "$concatArrays": [
            {
                "$filter": {
                    "input": existing,
                    "as": "entry",
                    "cond": {"$ne": [f"$$entry.{identity_field}", {"$literal": identity}]},
                }
            },
            {"$literal": [entry]},
        ]
    }
    if max_entries is not None:
        replacement = {
            "$cond": [
                {
                    "$or": [
                        {"$lt": [{"$size": existing}, max_entries]},
                        {
                            "$in": [
                                {"$literal": identity},
                                {"$ifNull": [f"${array_field}.{identity_field}", []]},
                            ]
                        },
                    ]
                },
                replacement,
                existing,
            ]
        }
    return [{"$set": {array_field: replacement}}]


async def save_named_entry(collection, selector, array_field, identity_field, identity, entry):
    update = named_array_update(array_field, identity_field, identity, entry)
    return await atomic_upsert(collection, selector, update)


async def next_sequence(collection, name):
    doc = await atomic_find_one_and_update(
        collection,
        {"_id": name},
        {"$inc": {"seq": 1}},
        return_document=ReturnDocument.AFTER,
        projection={"_id": 0, "seq": 1},
    )
    return doc["seq"]
