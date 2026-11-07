# tracks the buttons/state of anime settings

from pymongo import ReturnDocument

from Emilia.application import db
from Emilia.database.common import atomic_find_one_and_update


async def update_ui(chat_id, **values):
    if set(values) - {"cs", "bl"}:
        raise ValueError("Unknown anime UI setting")
    return await atomic_find_one_and_update(
        db.GROUP_UI,
        {"_id": str(chat_id)},
        [
            {
                "$set": {
                    "cs": {"$ifNull": ["$cs", "UPPER"]},
                    "bl": {"$cond": [{"$eq": [{"$type": "$bl"}, "missing"]}, "➤", "$bl"]},
                }
            },
            {"$set": {key: {"$literal": value} for key, value in values.items()}},
        ],
        return_document=ReturnDocument.AFTER,
    )
