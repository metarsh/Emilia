import functools
import inspect
import time
from typing import Any

from pyrogram import Client
from pyrogram.errors import RPCError
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden

LEFT_CHATS_ATTR = "_emilia_left_chats"
MAX_REMEMBERED = 64
MEMO_TTL = 300

_INSTALLED = False


def install_write_guard() -> None:
    global _INSTALLED

    if _INSTALLED:
        return

    for name in _write_methods():
        setattr(Client, name, _guard(getattr(Client, name)))

    Client.leave_chat = _memoized_leave(Client.leave_chat)

    _INSTALLED = True


def _write_methods() -> list[str]:
    names = []
    for name in dir(Client):
        if not name.startswith(("send_", "edit_message_", "forward_", "copy_")):
            continue
        member = getattr(Client, name, None)
        if not inspect.iscoroutinefunction(member):
            continue
        try:
            parameters = inspect.signature(member).parameters
        except (TypeError, ValueError):
            continue
        if "chat_id" in parameters:
            names.append(name)
    return names


def _guard(original):
    @functools.wraps(original)
    async def wrapper(self, *args, **kwargs):
        chat_id = _chat_id_of(args, kwargs)
        if chat_id is None:
            return await original(self, *args, **kwargs)

        memo = _left_chats(self)
        refused = _memo_hit(memo, chat_id)
        if refused is not None:
            raise refused

        try:
            return await original(self, *args, **kwargs)
        except ChatWriteForbidden as exc:
            await _leave_muted_chat(self, chat_id, memo, exc)
            raise

    return wrapper


def _memoized_leave(original):
    @functools.wraps(original)
    async def wrapper(self, chat_id, *args, **kwargs):
        if _memo_hit(getattr(self, LEFT_CHATS_ATTR, None), chat_id) is not None:
            return True
        return await original(self, chat_id, *args, **kwargs)

    return wrapper


def _chat_id_of(args, kwargs) -> Any:
    if "chat_id" in kwargs:
        return kwargs["chat_id"]
    return args[0] if args else None


def _left_chats(client) -> dict[Any, tuple[BaseException, float]] | None:
    memo = getattr(client, LEFT_CHATS_ATTR, None)
    if memo is not None:
        return memo

    try:
        memo = {}
        setattr(client, LEFT_CHATS_ATTR, memo)
    except (AttributeError, TypeError):
        return None
    return memo


def _memo_hit(memo, chat_id) -> BaseException | None:
    if memo is None:
        return None

    entry = memo.get(chat_id)
    if entry is None:
        return None

    exc, expires_at = entry
    if expires_at <= time.monotonic():
        memo.pop(chat_id, None)
        return None
    return exc


def _remember(memo, chat_id, exc) -> None:
    if memo is None:
        return
    memo[chat_id] = (exc.with_traceback(None), time.monotonic() + MEMO_TTL)
    while len(memo) > MAX_REMEMBERED:
        memo.pop(next(iter(memo)))


async def _leave_muted_chat(client, chat_id, memo, exc) -> None:
    if not isinstance(chat_id, int) or chat_id >= 0:
        return

    from Emilia.application import LOGGER

    LOGGER.warning(
        "chat_write_forbidden",
        extra={"emilia": {"event": "chat_write_forbidden", "chat_id": chat_id}},
    )
    try:
        await client.leave_chat(chat_id)
    except (RPCError, OSError) as e:
        LOGGER.warning("chat_write_forbidden: could not leave %s: %s", chat_id, e)
    finally:
        _remember(memo, chat_id, exc)
