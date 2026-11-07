# greetings (goodbye, welcome, captcha)

from Emilia.application import db
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr

welcome = db.welcome

DEFAUT_WELCOME = tr("welcome.hey_there_welcome_how")
DEFAUT_GOODBYE = tr("welcome.left_chat")


async def SetWelcome(chat_id, Content, Text, DataType):
    await atomic_upsert(
        welcome,
        {"chat_id": chat_id},
        {
            "$set": {
                "welcome_message.content": Content,
                "welcome_message.text": Text,
                "welcome_message.data_type": DataType,
            },
            "$setOnInsert": {"welcome": True, "clean_service": False},
        },
    )


async def UnSetWelcome(chat_id):
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$unset": {
                "welcome_message.content": 1,
                "welcome_message.text": 1,
                "welcome_message.data_type": 1,
            }
        },
    )


async def GetWelcome(chat_id):
    doc = await welcome.find_one(
        {"chat_id": chat_id},
        {"_id": 0, "welcome_message": 1},
    )
    if doc and doc.get("welcome_message") and "text" in doc["welcome_message"]:
        wm = doc["welcome_message"]
        return (wm.get("content"), wm.get("text"), wm.get("data_type"))


async def SetWelcomeMessageOnOff(chat_id, welcome_message):
    await atomic_upsert(welcome, {"chat_id": chat_id}, {"$set": {"welcome": welcome_message}})


async def GetWelcomemessageOnOff(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "welcome": 1})
    return doc.get("welcome", True) if doc else True


async def isWelcome(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "welcome_message.text": 1})
    return bool(doc and doc.get("welcome_message", {}).get("text"))


async def SetGoodBye(chat_id, Content, Text, DataType):
    await atomic_upsert(
        welcome,
        {"chat_id": chat_id},
        {
            "$set": {
                "goodbye_message.content": Content,
                "goodbye_message.text": Text,
                "goodbye_message.data_type": DataType,
            }
        },
    )


async def UnSetGoodbye(chat_id):
    await welcome.update_one(
        {"chat_id": chat_id},
        {
            "$unset": {
                "goodbye_message.content": 1,
                "goodbye_message.text": 1,
                "goodbye_message.data_type": 1,
            }
        },
    )


async def GetGoobye(chat_id):
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "goodbye_message": 1})
    if doc and doc.get("goodbye_message") and "text" in doc["goodbye_message"]:
        gm = doc["goodbye_message"]
        return (gm.get("content"), gm.get("text"), gm.get("data_type"))


async def SetGoodbyeMessageOnOff(chat_id, goodbye_message):
    await atomic_upsert(welcome, {"chat_id": chat_id}, {"$set": {"goodbye": goodbye_message}})


async def GetGoodbyemessageOnOff(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "goodbye": 1})
    return doc.get("goodbye", True) if doc else True


async def isGoodbye(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "goodbye_message.text": 1})
    return bool(doc and doc.get("goodbye_message", {}).get("text"))


async def SetCleanService(chat_id, clean_service):
    await atomic_upsert(welcome, {"chat_id": chat_id}, {"$set": {"clean_service": clean_service}})


async def GetCleanService(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "clean_service": 1})
    return doc.get("clean_service", False) if doc else False


async def SetCleanWelcome(chat_id, clean_welcome):
    await atomic_upsert(
        welcome,
        {"chat_id": chat_id},
        {"$set": {"clean_welcome": clean_welcome, "clean_welcome_message": None}},
    )


async def SetCleanWelcomeMessage(chat_id, message_id):
    await welcome.update_one({"chat_id": chat_id}, {"$set": {"clean_welcome_message": message_id}})


async def GetCleanWelcome(chat_id) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "clean_welcome": 1})
    return doc.get("clean_welcome", True) if doc else True


async def GetCleanWelcomeMessage(chat_id):
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "clean_welcome_message": 1})
    return doc.get("clean_welcome_message") if doc else None


async def SetCaptcha(chat_id, captcha):
    await atomic_upsert(welcome, {"chat_id": chat_id}, {"$set": {"captcha._captcha": captcha}})


async def isGetCaptcha(chat_id) -> bool:
    return (
        await welcome.find_one({"chat_id": chat_id, "captcha._captcha": True}, {"_id": 1})
        is not None
    )


async def GetCaptchaSettings(chat_id):
    doc = await welcome.find_one(
        {"chat_id": chat_id},
        {
            "_id": 0,
            "captcha.captcha_mode": 1,
            "captcha.captcha_text": 1,
            "captcha.captcha_kick_time": 1,
        },
    )
    return _captcha_settings((doc or {}).get("captcha") or {})


def _captcha_settings(settings):
    mode = settings.get("captcha_mode")
    if mode is None:
        mode = "button"
    elif mode not in {"button", "text", "math"}:
        raise ValueError("Unknown CAPTCHA mode")
    label = settings.get("captcha_text") or tr("welcome.click_here_prove_re_human")
    return mode, label, settings.get("captcha_kick_time")


async def get_captcha_policy(chat_id, user_id):
    cursor = await welcome.aggregate(
        [
            {"$match": {"chat_id": chat_id}},
            {"$limit": 1},
            {
                "$project": {
                    "_id": 0,
                    "captcha._captcha": 1,
                    "captcha.captcha_mode": 1,
                    "captcha.captcha_text": 1,
                    "verified": {
                        "$in": [
                            {"$literal": user_id},
                            {"$ifNull": ["$captcha.verified_users", []]},
                        ]
                    },
                    "reCaptcha": 1,
                    "rule_captcha": 1,
                }
            },
        ]
    )
    docs = await cursor.to_list(length=1)
    doc = docs[0] if docs else {}
    settings = doc.get("captcha") or {}
    mode, label, _ = _captcha_settings(settings)
    return {
        "enabled": bool(settings.get("_captcha")),
        "mode": mode,
        "label": label,
        "verified": bool(doc.get("verified")),
        "reverify": bool(doc.get("reCaptcha")),
        "rules": bool(doc.get("rule_captcha")),
    }


async def SetCaptchaText(chat_id, captcha_text):
    await atomic_upsert(
        welcome, {"chat_id": chat_id}, {"$set": {"captcha.captcha_text": captcha_text}}
    )


async def SetCaptchaMode(chat_id, captcha_mode):
    if captcha_mode not in {"button", "text", "math"}:
        raise ValueError("Unknown CAPTCHA mode")
    await atomic_upsert(
        welcome, {"chat_id": chat_id}, {"$set": {"captcha.captcha_mode": captcha_mode}}
    )


async def DeleteUsercaptchaData(chat_id, user_id):
    await welcome.update_one(
        {"chat_id": chat_id},
        {"$pull": {"captcha.users_welcomeIDs": {"user_id": user_id}}},
    )


async def AppendVerifiedUsers(chat_id, user_id):
    await atomic_upsert(
        welcome, {"chat_id": chat_id}, {"$addToSet": {"captcha.verified_users": user_id}}
    )


async def setReCaptcha(chat_id: int, reCaptcha: bool):
    await atomic_upsert(welcome, {"chat_id": chat_id}, {"$set": {"reCaptcha": reCaptcha}})


async def isReCaptcha(chat_id: int) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "reCaptcha": 1})
    return doc.get("reCaptcha", False) if doc else False


async def setRuleCaptcha(chat_id: int, rule_captcha: bool):
    await atomic_upsert(welcome, {"chat_id": chat_id}, {"$set": {"rule_captcha": rule_captcha}})


async def isRuleCaptcha(chat_id: int) -> bool:
    doc = await welcome.find_one({"chat_id": chat_id}, {"_id": 0, "rule_captcha": 1})
    return doc.get("rule_captcha", False) if doc else False
