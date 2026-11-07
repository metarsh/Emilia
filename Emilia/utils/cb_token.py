import secrets

import orjson

from Emilia.application import redis_client
from Emilia.utils.menu_guard import bot_namespace


async def stash(
    payload, ttl: int = 3600, *, client, user_id=None, chat_id=None, message_id=None
) -> str:
    token = secrets.token_urlsafe(12)
    binding = {
        k: str(v)
        for k, v in (("user", user_id), ("chat", chat_id), ("message", message_id))
        if v is not None
    }
    binding["bot"] = bot_namespace(client)
    record = {"binding": binding, "payload": payload}
    await redis_client.set(f"cbt:{token}", orjson.dumps(record).decode(), ex=ttl)
    return token


async def unstash(
    token: str, *, client, user_id=None, chat_id=None, message_id=None, consume: bool = False
):
    if not isinstance(token, str) or len(token) > 64:
        return None
    raw = await redis_client.get(f"cbt:{token}")
    if not raw:
        return None
    try:
        data = orjson.loads(raw)
    except orjson.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("binding"), dict):
        return None
    context = {
        k: str(v)
        for k, v in (("user", user_id), ("chat", chat_id), ("message", message_id))
        if v is not None
    }
    context["bot"] = bot_namespace(client)
    if data["binding"].get("bot") != context["bot"] or any(
        context.get(k) != v for k, v in data["binding"].items()
    ):
        return None
    payload = data.get("payload")
    if consume:
        claimed = await redis_client.eval(
            "if redis.call('GET', KEYS[1]) == ARGV[1] then "
            "return redis.call('DEL', KEYS[1]) end return 0",
            1,
            f"cbt:{token}",
            raw,
        )
        if not claimed:
            return None
    return payload
