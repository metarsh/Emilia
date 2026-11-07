import itertools
import re
import time
import traceback
from collections.abc import Callable
from functools import wraps

import pyrogram
from pyrogram.enums import ChatType
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden
from pyrogram.filters import Filter, create
from pyrogram.handlers import CallbackQueryHandler
from redis.exceptions import RedisError

from Emilia.application import LOGGER, pgram
from Emilia.config import Config
from Emilia.locales import tr
from Emilia.utils.ads import (
    mark_pyrogram_command_message,
    reset_ad_context,
    set_ad_context,
)
from Emilia.utils.auth import is_dev, is_owner
from Emilia.utils.chat_context import reset_context, restore_context
from Emilia.utils.client_context import bot_username
from Emilia.utils.command_help import COMMAND_HELP, attach_command_help, reply_usage
from Emilia.utils.command_policy import CHAT_SCOPES, check_chat_scope, enforce_rate_limit
from Emilia.utils.connections import ConnectionAccessDenied
from Emilia.utils.errors import forward_traceback, telegram_error_text
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.metrics import track_command
from Emilia.utils.trace import TRACE_ID

DISABLE_COMMANDS = []
CONNECTED_COMMANDS = {}
_GROUP_SEQ = itertools.count(1000)
_PENDING_LISTENERS = []

_COMMAND_TOKEN_RE = re.compile(r"([^\s]+)([\s\S]*)")
_ARGUMENT_RE = re.compile(r"([\"'])(.*?)(?<!\\)\1|(\S+)")


def unified_wrapper(
    func,
    command_name: str,
    *,
    limit=None,
    chat_scope="any",
    allow_connected=False,
    access="public",
    require_reply=False,
    callback_access=CallbackAccess(),
):
    if getattr(func, "_emilia_command_name", None) == command_name:
        if command_name != "callback_query":
            return func
        registrations = getattr(func, "handlers", [])
        func = func.__wrapped__
    else:
        registrations = []

    @wraps(func)
    async def wrapper(client, update, *args, **kwargs):
        user = getattr(update, "from_user", None)
        user_id = user.id if user else None

        if command_name in {"callback_query", "inline_query"}:
            message = getattr(update, "message", None)
        else:
            message = update
        chat = getattr(message, "chat", None)
        chat_id = chat.id if chat else None
        message_id = getattr(message, "id", None)
        previous_context = reset_context(message)

        start_time = time.perf_counter()

        trace = f"{chat_id}:{message_id}"
        metadata = {
            "command": command_name,
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "trace": trace,
        }
        trace_token = TRACE_ID.set(trace)
        help_token = COMMAND_HELP.set(func if hasattr(func, "usage") else COMMAND_HELP.get())

        ad_token = set_ad_context(
            chat_id,
            command_name not in {"callback_query", "inline_query"} and _is_group_message(message),
        )

        if command_name == "callback_query":
            update._emilia_handled = True

        try:
            if command_name == "callback_query" and not await callback_access.allows(
                client, update
            ):
                return
            if access != "public" and not (
                is_dev(user_id) if access == "developer" else is_owner(user_id)
            ):
                if hasattr(update, "reply_text"):
                    await update.reply_text(
                        tr(
                            "errors.developer_only"
                            if access == "developer"
                            else "errors.owner_only"
                        )
                    )
                return
            if command_name not in {"callback_query", "inline_query"}:
                if not await check_chat_scope(update, chat_scope, allow_connected=allow_connected):
                    return
            if not await enforce_rate_limit(
                client, update, f"{func.__module__}.{func.__qualname__}", limit
            ):
                return
            if require_reply and not update.reply_to_message:
                await reply_usage(update, func)
                return
            result = await func(client, update, *args, **kwargs)
        except ConnectionAccessDenied as error:
            from Emilia.utils.command_policy import answer_denial

            await answer_denial(update, str(error), alert=True)
            return
        except (pyrogram.StopPropagation, pyrogram.ContinuePropagation):
            raise
        except pyrogram.errors.MessageNotModified:
            return
        except ChatWriteForbidden as e:
            LOGGER.warning(
                "command_write_forbidden",
                extra={
                    "emilia": {
                        **metadata,
                        "event": "command_write_forbidden",
                        "duration": time.perf_counter() - start_time,
                        "error": str(e),
                    }
                },
            )
            return
        except Exception as e:
            error_text = telegram_error_text(e)
            if error_text:
                LOGGER.warning(
                    "command_rejected",
                    extra={"emilia": {**metadata, "event": "command_rejected", "error": str(e)}},
                )
                try:
                    if command_name == "callback_query":
                        await update.answer(error_text, show_alert=True)
                    elif command_name != "inline_query":
                        await update.reply_text(error_text)
                except pyrogram.errors.RPCError:
                    pass
                return
            error_traceback = traceback.format_exc()
            LOGGER.error(
                "command_error",
                extra={
                    "emilia": {
                        **metadata,
                        "event": "command_error",
                        "duration": time.perf_counter() - start_time,
                        "error": str(e),
                        "traceback": error_traceback,
                    }
                },
            )
            await forward_traceback(
                command_name,
                error_traceback,
                f"User: {user_id} | Chat: {chat_id} | Trace: {trace}",
            )
            try:
                if command_name == "callback_query":
                    await update.answer(tr("custom_filter.something_went_wrong"), show_alert=False)
                elif command_name != "inline_query":
                    await update.reply_text(
                        tr("custom_filter.something_went_wrong_running_that_command_the")
                    )
            except pyrogram.errors.RPCError:
                pass
            return
        finally:
            restore_context(message, previous_context)
            reset_ad_context(ad_token)
            TRACE_ID.reset(trace_token)
            COMMAND_HELP.reset(help_token)
            try:
                await track_command(command_name)
            except RedisError as e:
                LOGGER.warning(
                    "command_metrics_error",
                    extra={
                        "emilia": {**metadata, "event": "command_metrics_error", "error": str(e)}
                    },
                )

        duration = time.perf_counter() - start_time
        payload = {
            "emilia": {
                **metadata,
                "event": "command_success",
                "duration": duration,
            }
        }
        if duration > 2.0:
            LOGGER.info("command_slow", extra=payload)
        else:
            LOGGER.debug("command_success", extra=payload)
        return result

    wrapper._emilia_command_name = command_name
    if command_name == "callback_query":
        wrapper.handlers = list(registrations)
    return wrapper


def _is_group_message(message) -> bool:
    chat = getattr(message, "chat", None)
    chat_type = getattr(chat, "type", None)
    return chat_type in (ChatType.GROUP, ChatType.SUPERGROUP)


def _parse_arguments(text: str) -> list[str]:
    return [
        re.sub(r"\\([\"'])", r"\1", match.group(2) or match.group(3) or "")
        for match in _ARGUMENT_RE.finditer(text)
    ]


def _command_filter(
    commands: str | list[str] | None = None,
    prefixes: str | list[str] | tuple[str, ...] | None = Config.TRIGGERS,
    case_sensitive: bool = False,
    *,
    pattern: str | None = None,
    check_bot2bot: bool = True,
) -> Filter:
    if (commands is None) == (pattern is None):
        raise ValueError("Provide either commands or pattern, but not both")

    entries = [commands] if isinstance(commands, str) else commands
    names = list(dict.fromkeys(name.split("@", 1)[0] for name in entries or []))
    if not case_sensitive:
        names = list(dict.fromkeys(name.lower() for name in names))
    command_pattern = (
        pattern if pattern is not None else "|".join(re.escape(name) for name in names)
    )

    entries = [prefixes] if isinstance(prefixes, str) else prefixes
    normalized_prefixes = tuple(
        sorted(set(entries or [""]), key=lambda prefix: (-len(prefix), prefix))
    )
    prefix_pattern = "|".join(re.escape(prefix) for prefix in normalized_prefixes)
    compiled = re.compile(
        rf"^(?:{prefix_pattern})(?:{command_pattern})(?:\s+|$)([\s\S]*)$",
        0 if case_sensitive else re.IGNORECASE,
    )

    async def func(flt, client, message):
        text = message.text or message.caption
        message.command = None
        message.matches = None
        if not text:
            return False

        for prefix in flt.prefixes:
            if not text.startswith(prefix):
                continue
            token_match = _COMMAND_TOKEN_RE.match(text[len(prefix) :])
            if not token_match:
                continue
            token, tail = token_match.groups()
            if "@" in token:
                token, mentioned = token.split("@", 1)
                if mentioned.lower() != bot_username(client).lower():
                    return False

            match = flt.compiled.match(prefix + token + tail)
            if not match or (flt.pattern is None and not flt.commands):
                continue

            command_name = token if flt.case_sensitive else token.lower()
            if flt.pattern is None:
                command_name = next(
                    (
                        name
                        for name in flt.commands
                        if re.fullmatch(re.escape(name), token, flt.compiled.flags)
                    ),
                    None,
                )
                if command_name is None:
                    continue
            message.command = [command_name] + _parse_arguments(match.groups()[-1])
            message.matches = [match]
            if flt.check_bot2bot:
                from Emilia.utils.bot2bot import bot_command_allowed

                if not await bot_command_allowed(message, flt.pattern or command_name):
                    return False
            mark_pyrogram_command_message(message, _is_group_message(message))
            return True
        return False

    return create(
        func,
        "CommandFilter",
        compiled=compiled,
        commands=names,
        prefixes=normalized_prefixes,
        case_sensitive=case_sensitive,
        pattern=pattern,
        check_bot2bot=check_bot2bot,
    )


def _handler_decorator(
    command_name: str,
    *registrations: Callable,
    limit=Config.RATE_LIMIT_GENERAL,
    chat_scope="any",
    allow_connected=False,
    metadata=None,
    access="public",
    require_reply=False,
    callback_access=CallbackAccess(),
):

    def decorator(func):
        if metadata is not None:
            attach_command_help(func, command_name, **metadata)
        wrapped_func = unified_wrapper(
            func,
            command_name,
            limit=limit,
            chat_scope=chat_scope,
            allow_connected=allow_connected,
            access=access,
            require_reply=require_reply,
            callback_access=callback_access,
        )
        for registration in registrations:
            registration(wrapped_func)
        return wrapped_func

    return decorator


def command(
    commands: str | list[str] | None = None,
    prefixes: str | list[str] | tuple[str, ...] | None = Config.TRIGGERS,
    case_sensitive: bool = False,
    disable: bool = False,
    *,
    pattern: str | None = None,
    filters: Filter | None = None,
    group: int = 0,
    chat_scope: str = "any",
    allow_connected: bool = False,
    rate_limit: tuple[int, float] | None = Config.RATE_LIMIT_GENERAL,
    usage: str | None = None,
    description: str | None = None,
    example: str | None = None,
    access: str = "public",
    require_reply: bool = False,
):
    if chat_scope not in CHAT_SCOPES:
        raise ValueError(f"Unknown command chat scope: {chat_scope}")
    if access not in {"public", "developer", "owner"}:
        raise ValueError(f"Unknown command access policy: {access}")
    if allow_connected and chat_scope == "private":
        raise ValueError("Connected chats require a compatible target scope")
    command_filter = _command_filter(commands, prefixes, case_sensitive, pattern=pattern)
    aliases = command_filter.commands if pattern is None else pattern.split("|")
    if disable:
        names = ([pattern] if pattern is not None else []) + list(aliases)
        DISABLE_COMMANDS.extend(name for name in names if name not in DISABLE_COMMANDS)
    if filters is not None:
        command_filter = filters & command_filter
    entries = [commands] if isinstance(commands, str) else commands
    command_name = pattern if pattern is not None else "|".join(entries or [])
    if allow_connected:
        CONNECTED_COMMANDS.update(
            {name: chat_scope for name in aliases if re.fullmatch(r"[a-z0-9]+", name)}
        )
    registration = _handler_decorator(
        command_name,
        pyrogram.Client.on_message(command_filter, group=group),
        limit=rate_limit,
        chat_scope=chat_scope,
        allow_connected=allow_connected,
        metadata={"usage": usage, "description": description, "example": example},
        access=access,
        require_reply=require_reply,
    )
    if not disable:
        return registration

    def decorator(func):
        from Emilia.utils.disable import disable as disable_command

        attach_command_help(
            func, command_name, usage=usage, description=description, example=example
        )
        return registration(disable_command(func))

    return decorator


def _query_filter(pattern: str | None):
    return pyrogram.filters.regex(rf"\A(?:{pattern})") if pattern else None


def callbackquery(
    pattern: str | None = None,
    *,
    filters: Filter | None = None,
    group: int = 0,
    rate_limit=Config.RATE_LIMIT_GENERAL,
    access: CallbackAccess = CallbackAccess(),
):
    if not isinstance(access, CallbackAccess):
        raise TypeError("Callback access must be a CallbackAccess policy")
    query_filter = _query_filter(pattern)
    if filters is not None:
        query_filter = filters if query_filter is None else filters & query_filter
    return _handler_decorator(
        "callback_query",
        pyrogram.Client.on_callback_query(query_filter, group=group),
        limit=rate_limit,
        callback_access=access,
    )


def auth(pattern: str):
    filters = _command_filter(pattern=pattern, check_bot2bot=False)
    return _handler_decorator(
        pattern,
        pyrogram.Client.on_message(filters, group=0),
        pyrogram.Client.on_edited_message(filters, group=0),
        metadata={},
        access="developer",
    )


def inlinequery(
    pattern: str | None = None,
    *,
    filters: Filter | None = None,
    group: int = 0,
    rate_limit=Config.RATE_LIMIT_GENERAL,
):
    query_filter = _query_filter(pattern)
    if filters is not None:
        query_filter = filters if query_filter is None else filters & query_filter
    return _handler_decorator(
        "inline_query", pyrogram.Client.on_inline_query(query_filter, group=group), limit=rate_limit
    )


def listen(filters=None, name: str | None = None):
    def decorator(func):
        wrapped_func = unified_wrapper(func, command_name=name or func.__name__)
        _PENDING_LISTENERS.append(
            (
                pyrogram.handlers.MessageHandler(wrapped_func, filters),
                next(_GROUP_SEQ),
            )
        )
        return wrapped_func

    return decorator


_EXPIRED_CB_GROUP = 999999


async def _expired_callback_catchall(client, query):
    if getattr(query, "_emilia_handled", False):
        return
    try:
        await query.answer(tr("custom_filter.this_button_has_expired"), cache_time=5)
    except pyrogram.errors.RPCError:
        pass


def register_expired_callback_catchall(client):
    client.add_handler(
        CallbackQueryHandler(_expired_callback_catchall, None), group=_EXPIRED_CB_GROUP
    )


flush_pending_handlers_called = False


def flush_pending_handlers():
    global flush_pending_handlers_called
    if flush_pending_handlers_called:
        return
    flush_pending_handlers_called = True

    for handler, group in _PENDING_LISTENERS:
        pgram.add_handler(handler, group)
    _PENDING_LISTENERS.clear()

    register_expired_callback_catchall(pgram)
