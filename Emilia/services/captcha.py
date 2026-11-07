import re
import secrets
from datetime import UTC, datetime, timedelta

from Emilia.application import db
from Emilia.locales import tr
from Emilia.utils.client_context import bot_id
from Emilia.utils.tasks import finish_cleanup

MAX_ATTEMPTS = 3
CHALLENGE_TTL = timedelta(minutes=15)


def _key(client, chat_id, user_id):
    return f"{bot_id(client)}:{chat_id}:{user_id}"


def start_payload(message):
    parts = (message.text or "").split(maxsplit=1)
    match = (
        re.fullmatch(r"captcha_(button|text|math)_(?:(\d+)_(-?\d+)_)?([A-Za-z0-9_-]{16})", parts[1])
        if len(parts) == 2
        else None
    )
    if match:
        mode, user, chat, token = match.groups()
        return mode, int(user) if user else None, int(chat) if chat else None, token
    return None


async def from_link(client, message, payload):
    _, user_id, chat_id, token = payload
    if user_id is not None and user_id != message.from_user.id:
        await message.reply(tr("text_captcha.this_wasn_t_for_you"))
        return None
    query = {
        "bot_id": bot_id(client),
        "user_id": message.from_user.id,
        "token": token,
        "expires_at": {"$gt": datetime.now(UTC)},
    }
    if chat_id is not None:
        query["chat_id"] = chat_id
    challenge = await db.captcha_challenges.find_one(query)
    if not challenge:
        await message.reply(tr("captcha.expired_prompt"))
        return None
    if challenge["claimed"]:
        await message.reply(tr("captcha.processing"))
        return None
    return challenge


def _state(challenge, claimed):
    return {
        "_id": challenge["_id"],
        "token": challenge["token"],
        "claimed": claimed,
        "stage": challenge["stage"],
        "expires_at": {"$gt": datetime.now(UTC)},
        "attempts": challenge["attempts"],
        "answer": challenge.get("answer"),
        "prompt_chat_id": challenge.get("prompt_chat_id"),
        "prompt_message_id": challenge.get("prompt_message_id"),
    }


async def begin(
    client,
    chat_id,
    user_id,
    mode,
    *,
    welcome_id=0,
    source="member",
    rules=False,
    private_chat_id=None,
    chat_title=None,
):
    if mode not in {"button", "text", "math", "rules"}:
        raise ValueError("Unknown CAPTCHA mode")
    challenge = {
        "_id": _key(client, chat_id, user_id),
        "bot_id": bot_id(client),
        "chat_id": chat_id,
        "user_id": user_id,
        "private_chat_id": private_chat_id or user_id,
        "chat_title": chat_title,
        "token": secrets.token_urlsafe(12),
        "welcome_id": welcome_id,
        "source": source,
        "stage": mode,
        "mode": mode,
        "rules": rules,
        "attempts": 0,
        "claimed": False,
        "expires_at": datetime.now(UTC) + CHALLENGE_TTL,
    }
    await db.captcha_challenges.replace_one({"_id": challenge["_id"]}, challenge, upsert=True)
    return challenge


async def get(client, chat_id, user_id):
    return await db.captcha_challenges.find_one(
        {
            "_id": _key(client, chat_id, user_id),
            "expires_at": {"$gt": datetime.now(UTC)},
            "claimed": False,
        }
    )


async def bind_prompt(challenge, message, *, stage=None, **changes):
    changes.update(prompt_chat_id=message.chat.id, prompt_message_id=message.id, claimed=False)
    if stage:
        changes["stage"] = stage
    result = await db.captcha_challenges.update_one(
        _state(challenge, challenge.get("claimed", False)),
        {"$set": changes},
    )
    if not result.matched_count:
        return False
    challenge.update(changes)
    return True


async def bind_welcome(challenge, message):
    if await bind_prompt(challenge, message, welcome_id=message.id):
        return True
    # A private challenge may already be open; only attach the welcome ID.
    result = await db.captcha_challenges.update_one(
        {
            "_id": challenge["_id"],
            "token": challenge["token"],
            "expires_at": {"$gt": datetime.now(UTC)},
        },
        {"$set": {"welcome_id": message.id}},
    )
    return bool(result.matched_count)


async def pending_welcome(client, chat_id, message_id):
    return (
        await db.captcha_challenges.find_one(
            {
                "bot_id": bot_id(client),
                "chat_id": chat_id,
                "welcome_id": message_id,
                "expires_at": {"$gt": datetime.now(UTC)},
            },
            {"_id": 1},
        )
        is not None
    )


async def verifying_join_request(client, chat_id, user_id):
    return (
        await db.captcha_challenges.find_one(
            {
                "_id": _key(client, chat_id, user_id),
                "source": "join_request",
                "claimed": True,
                "expires_at": {"$gt": datetime.now(UTC)},
            },
            {"_id": 1},
        )
        is not None
    )


async def from_prompt(client, user_id, token, message, stages):
    if not message or not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16}", token):
        return None
    challenge = await db.captcha_challenges.find_one(
        {
            "bot_id": bot_id(client),
            "user_id": user_id,
            "token": token,
            "expires_at": {"$gt": datetime.now(UTC)},
        }
    )
    if (
        not challenge
        or challenge["stage"] not in stages
        or challenge.get("prompt_chat_id") != message.chat.id
        or challenge.get("prompt_message_id") != message.id
    ):
        return None
    return challenge


async def from_callback(client, query, token, stages):
    query._emilia_handled = True
    challenge = (
        await from_prompt(client, query.from_user.id, token, query.message, stages)
        if query.from_user
        else None
    )
    if not challenge:
        await query.answer(tr("captcha.expired_prompt"), show_alert=True)
        return None
    if challenge["claimed"]:
        await query.answer(tr("captcha.processing"))
        return None
    return challenge


async def is_current(challenge):
    return await db.captcha_challenges.find_one(_state(challenge, True), {"_id": 1}) is not None


async def claim(challenge):
    result = await db.captcha_challenges.update_one(
        _state(challenge, False),
        {"$set": {"claimed": True}},
    )
    if not result.modified_count:
        return False
    challenge["claimed"] = True
    return True


async def release(challenge, **changes):
    result = await db.captcha_challenges.update_one(
        {"_id": challenge["_id"], "token": challenge["token"], "claimed": True},
        {"$set": {"claimed": False, **changes}},
    )
    if result.matched_count:
        challenge.update(claimed=False, **changes)


async def remove(challenge):
    await db.captcha_challenges.delete_one({"_id": challenge["_id"], "token": challenge["token"]})


async def invalidate(client, chat_id, user_id):
    await db.captcha_challenges.delete_one({"_id": _key(client, chat_id, user_id)})


async def complete(client, challenge, *, claimed=False):
    from Emilia.modules.greetings.utils.actions import passedAction

    if not claimed and not await claim(challenge):
        return False
    try:
        await passedAction(
            client,
            challenge["chat_id"],
            challenge["user_id"],
            challenge["welcome_id"],
            source=challenge["source"],
            challenge=challenge,
        )
    except BaseException:
        await finish_cleanup(release(challenge))
        raise
    await remove(challenge)
    return True
