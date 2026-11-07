# save and get birthdays

from Emilia.application import db
from Emilia.database.common import atomic_upsert

birthday_collection = db.birthday


async def set_birthday(user_id: int, day: int, month: int, chat_id: int = None):
    operation = {
        "$set": {
            "day": day,
            "month": month,
        }
    }
    if chat_id:
        operation["$addToSet"] = {"chats": chat_id}

    await atomic_upsert(birthday_collection, {"user_id": user_id}, operation)


async def get_birthday(user_id: int):
    return await birthday_collection.find_one({"user_id": user_id})


async def delete_birthday(user_id: int):
    await birthday_collection.delete_one({"user_id": user_id})


def get_birthdays_by_date(day: int, month: int):
    return birthday_collection.find({"day": day, "month": month})
