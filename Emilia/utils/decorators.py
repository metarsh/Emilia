import asyncio
import html
import secrets
from datetime import UTC, datetime
from functools import wraps

from pymongo.errors import PyMongoError
from pyrogram import Client, enums, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError
from pyrogram.errors.exceptions.forbidden_403 import ChatWriteForbidden
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
)
from redis.exceptions import RedisError

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.database.chats_settings import get_anon_setting_cached
from Emilia.locales import tr
from Emilia.utils.cache import SimpleCache
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.client_context import bot_id
from Emilia.utils.get_user import mention_html
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_id, actor_name, actor_user, is_anonymous_admin
from Emilia.utils.message_links import message_reference

# log channel stuff
mongo_collection = db.logchannels

_logch_cache = SimpleCache(default_ttl=300, namespace="logchannels")


async def _get_log_channel_id(chat_id):
    """Return the configured log channel id for chat_id, or None. Cached."""
    key = f"logch:{chat_id}"
    cached = await _logch_cache.get(key)
    if cached is not None:
        return None if cached == "none" else cached
    chat_data = await mongo_collection.find_one({"chat_id": chat_id})
    channel_id = chat_data["channel_id"] if chat_data and "channel_id" in chat_data else None
    await _logch_cache.set(key, "none" if channel_id is None else channel_id)
    return channel_id


async def invalidate_log_channel_cache(chat_id):
    await _logch_cache.delete(f"logch:{chat_id}")


def get_telegram_info(event):
    id_ = "connected"
    if not hasattr(event, "chat"):
        return (None, None, None, None, "manual")
    if not event.chat.type == enums.ChatType.PRIVATE:
        try:
            id_ = event.id
        except AttributeError:
            id_ = "manual"

    admin_id = actor_id(event)
    first_name = actor_name(event) if admin_id is not None else None

    chat_id = event.chat.id

    if event.chat.type == enums.ChatType.PRIVATE:
        connected = getattr(event, "_emilia_target_chat_id", None)
        if connected:
            chat_id = connected
            id_ = "connected"
            title = effective_chat(event).title or "Chat"
        else:
            # PM with no connection
            title = (
                event.chat.title if hasattr(event.chat, "title") else tr("decorators.private_chat")
            )
            chat_id = None
            id_ = "manual"
    else:
        title = effective_chat(event).title or "Chat"

    return (chat_id, title, first_name, admin_id, id_)


def log_to_channel(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        log_message = " "
        client = args[0]
        event = args[1] if args[1] is not None else args[0]

        chat_id, chat_title, admin_name, admin_id, message_id = get_telegram_info(event)

        if chat_id is None:
            return await func(*args, **kwargs)

        channel_id = await _get_log_channel_id(chat_id)
        if channel_id is None:
            return await func(*args, **kwargs)

        result = await func(*args, **kwargs)

        if not isinstance(result, tuple):
            return result

        if len(result) == 3:
            event_type, user_id, user_name = result
        elif len(result) == 5:
            event_type, user_id, user_name, admin_id, admin_name = result
        else:
            LOGGER.error("log_to_channel: bad result tuple %r", result)
            return result

        datetime_fmt = "%H:%M - %d-%m-%Y"

        log_message += f"<b>{html.escape(chat_title or 'Chat')}</b> <code>{chat_id}</code>\n#{html.escape(event_type or '')}\n"

        if admin_name and admin_id is not None:
            log_message += tr(
                "decorators.admin_tg_user_id",
                mention=mention_html(admin_id, admin_name, client=client),
            )
        if user_name and user_id:
            log_message += tr(
                "decorators.user_tg_user_id",
                mention=mention_html(user_id, user_name, client=client),
            )

        if user_id:
            log_message += tr("decorators.user_id", user_id=user_id)

        log_message += tr(
            "decorators.event_stamp", datetime_fmt=datetime.now(UTC).strftime(datetime_fmt)
        )

        try:
            if message_id and message_id not in ("connected", "manual") and event.link:
                log_message += tr(
                    "decorators.link_click_here",
                    reference=message_reference(event, "click here", html=True),
                )
            elif message_id == "connected":
                log_message += tr("decorators.link_no_message_link_connected_commands")
            elif message_id == "manual":
                log_message += tr("decorators.link_no_message_link_manual_actions")
        except AttributeError:
            pass

        await client.send_message(
            channel_id,
            log_message,
            parse_mode=enums.ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return result

    return wrapper


async def _invalidate_admin_caches(chat_id, user_id, *, client=None):
    try:
        from Emilia.utils.cache import admin_cache
        from Emilia.utils.client_context import bot_id

        if client is None:
            await admin_cache.clear()
        else:
            await admin_cache.delete(f"chat_member:{bot_id(client)}:{chat_id}:{user_id}")

        from Emilia.utils.admins import cache_collection

        selector = {"chat_id": chat_id, "user_id": user_id}
        if client is not None:
            selector["bot_id"] = bot_id(client)
        await cache_collection.delete_many(selector)
    except (RedisError, PyMongoError):
        LOGGER.warning("Failed to invalidate admin caches", exc_info=True)


@Client.on_chat_member_updated(filters.group)
@log_to_channel
async def NewMemer(client: Client, message: ChatMemberUpdated):
    from Emilia.utils.chat_status import member_is_admin, member_is_present

    old = message.old_chat_member
    new = message.new_chat_member
    member = new or old
    peer = (member.user or member.chat) if member else None
    if peer is None:
        return
    await _invalidate_admin_caches(message.chat.id, peer.id, client=client)
    issuer = message.from_user
    if issuer and issuer.id == bot_id(client):
        return

    event = None
    if (
        new
        and new.status == ChatMemberStatus.BANNED
        and (not old or old.status != ChatMemberStatus.BANNED)
    ):
        event = "BAN"
    elif (
        old
        and old.status == ChatMemberStatus.BANNED
        and (not new or new.status != ChatMemberStatus.BANNED)
    ):
        event = "UNBAN"
    elif not member_is_present(old) and member_is_present(new):
        event = "WELCOME"
    elif member_is_present(old) and not member_is_present(new):
        event = "GOODBYE"
    elif not member_is_admin(old) and member_is_admin(new):
        event = "PROMOTE"
    elif member_is_admin(old) and not member_is_admin(new):
        event = "DEMOTE"

    if event is None:
        return
    name = peer.first_name if member.user else peer.title
    return (
        event,
        peer.id,
        name,
        issuer.id if issuer else None,
        issuer.first_name if issuer else None,
    )


def rate_limit(limit_config=Config.RATE_LIMIT_GENERAL):

    def decorator(func):
        @wraps(func)
        async def wrapper(client, update, *args, **kwargs):
            from Emilia.utils.command_policy import enforce_rate_limit

            if not await enforce_rate_limit(
                client, update, f"{func.__module__}.{func.__qualname__}", limit_config
            ):
                return None
            return await func(client, update, *args, **kwargs)

        return wrapper

    return decorator


# leave chat if cannot write
def leavemute(func):
    @wraps(func)
    async def capture(client, message, *args, **kwargs):
        try:
            return await func(client, message, *args, **kwargs)
        except ChatWriteForbidden:
            await client.leave_chat(message.chat.id)
            return

    return capture


callback_registry = {}


def _remove_callback_handler(client, registered_handler):
    if registered_handler is None:
        return
    client.remove_handler(*registered_handler)


async def _expire_callback_handler(client, callback_name, registered_handler, delay=300):
    await asyncio.sleep(delay)
    if callback_registry.pop(callback_name, None) is not None:
        _remove_callback_handler(client, registered_handler)


def register_callback(
    func, message, prompt, client, owner_only: bool = False, *, args=(), kwargs=None
):
    from Emilia.custom_filter import unified_wrapper
    from Emilia.utils.command_help import COMMAND_HELP

    command_help = COMMAND_HELP.get()
    callback_name = f"anon:{secrets.token_urlsafe(8)}"
    registered_handler = None
    source_text = message.text or message.caption or ""
    target_chat_id = effective_chat_id(message)

    async def callback_handler(_: Client, callback_query: CallbackQuery):
        user_id = callback_query.from_user.id
        chat_id = callback_query.message.chat.id
        if chat_id != prompt.chat.id or callback_query.message.id != prompt.id:
            await callback_query.answer(
                tr("decorators.this_confirmation_belongs_to_another_chat"),
                show_alert=True,
            )
            return

        source = await client.get_messages(message.chat.id, message.id)
        if (
            not source
            or getattr(source, "empty", False)
            or not is_anonymous_admin(source)
            or (source.text or source.caption or "") != source_text
        ):
            return await callback_query.answer(
                tr("decorators.this_confirmation_has_expired"), show_alert=True
            )
        if callback_registry.pop(callback_name, None) is None:
            await callback_query.answer(
                tr("decorators.this_confirmation_has_expired"), show_alert=True
            )
            return
        _remove_callback_handler(client, registered_handler)
        message._emilia_verified_user_id = user_id
        message._emilia_verified_user = callback_query.from_user
        await callback_query.answer()
        help_token = COMMAND_HELP.set(command_help)
        try:
            await func(_, message, *args, **(kwargs or {}))
        finally:
            COMMAND_HELP.reset(help_token)
            del message._emilia_verified_user_id
            del message._emilia_verified_user
        try:
            await callback_query.message.delete()
        except RPCError:
            pass

    registered_handler = client.add_handler(
        CallbackQueryHandler(
            unified_wrapper(
                callback_handler,
                "callback_query",
                limit=Config.RATE_LIMIT_GENERAL,
                callback_access=CallbackAccess(chat_id=target_chat_id, owner=owner_only),
            ),
            filters.create(lambda _, __, query: query.data == callback_name),
        )
    )
    callback_registry[callback_name] = True
    from Emilia.utils.tasks import spawn

    spawn(
        _expire_callback_handler(client, callback_name, registered_handler),
        name=f"expire_callback:{callback_name}",
    )

    return callback_name


def anonadmin_checker(
    func=None, *, owner_only: bool = False, named: bool = False, allow_channel: bool = False
):

    def decorator(inner_func):
        @wraps(inner_func)
        async def wrapper(client, message, *args, **kwargs):
            if actor_user(message) is not None:
                return await inner_func(client, message, *args, **kwargs)
            if is_anonymous_admin(message):
                if not owner_only and not named and await get_anon_setting_cached(message.chat.id):
                    message._emilia_anonymous_admin_allowed = True
                    return await inner_func(client, message, *args, **kwargs)

                button_text = (
                    tr("decorators.click_prove_owner")
                    if owner_only
                    else tr("decorators.click_prove_admin")
                )
                prompt = await message.reply_text(
                    tr("decorators.you_are_anonymous_tap_this_button_to")
                )
                button = [
                    [
                        InlineKeyboardButton(
                            text=button_text,
                            callback_data=register_callback(
                                inner_func,
                                message,
                                prompt,
                                client,
                                owner_only=owner_only,
                                args=args,
                                kwargs=kwargs,
                            ),
                        )
                    ]
                ]
                await prompt.edit_reply_markup(InlineKeyboardMarkup(button))

                return
            elif message.sender_chat:
                if allow_channel:
                    return await inner_func(client, message, *args, **kwargs)
                return await message.reply_text(tr("channels.named_admin_required"))
            else:
                return await inner_func(client, message, *args, **kwargs)

        return wrapper

    if func is None:
        return decorator
    return decorator(func)
