from Emilia.config import Config


def bot_id(client) -> int:
    me = getattr(client, "me", None)
    identity = getattr(me, "id", None) or getattr(client, "bot_id", None)
    if identity:
        return int(identity)
    token = getattr(client, "bot_token", None) or Config.TOKEN
    return int(token.split(":", 1)[0]) if token else Config.BOT_ID


def bot_username(client=None) -> str:
    username = getattr(getattr(client, "me", None), "username", None) or Config.BOT_USERNAME
    return username.removeprefix("@")


def bot_name(client) -> str:
    if getattr(client, "is_clone", False):
        return getattr(getattr(client, "me", None), "first_name", None) or Config.BOT_NAME
    return Config.BOT_NAME
