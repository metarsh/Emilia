# rules for a group chat

from Emilia.application import db
from Emilia.database.common import atomic_upsert

rules = db.rules


async def set_rules_db(chat_id, chat_rules):
    await atomic_upsert(
        rules,
        {"chat_id": chat_id},
        {
            "$set": {"rules": chat_rules},
            "$setOnInsert": {"private_note": True, "button_text": "Rules"},
        },
    )


async def get_rules(chat_id: int):
    doc = await rules.find_one({"chat_id": chat_id}, {"_id": 0, "rules": 1})
    return doc.get("rules") if doc else None


async def set_private_rule(chat_id, private_note):
    await atomic_upsert(
        rules,
        {"chat_id": chat_id},
        {
            "$set": {"private_note": private_note},
            "$setOnInsert": {"rules": None, "button_text": "Rules"},
        },
    )


async def get_private_note(chat_id) -> bool:
    doc = await rules.find_one({"chat_id": chat_id}, {"_id": 0, "private_note": 1})
    return doc.get("private_note", True) if doc else True


async def set_rule_button(chat_id, rule_button):
    await atomic_upsert(
        rules,
        {"chat_id": chat_id},
        {
            "$set": {"button_text": rule_button},
            "$setOnInsert": {"rules": None, "private_note": True},
        },
    )


async def get_rules_button(chat_id):
    doc = await rules.find_one({"chat_id": chat_id}, {"_id": 0, "button_text": 1})
    return doc.get("button_text", "Rules") if doc else "Rules"
