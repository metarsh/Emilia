import inspect
import secrets
from hashlib import sha256

from pyrogram import ContinuePropagation, StopPropagation
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.handlers import MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.application import LOGGER
from Emilia.database.bot2bot import add_pending_bot_command, get_bot2bot_settings
from Emilia.locales import tr
from Emilia.utils.chat_status import has_chat_permission
from Emilia.utils.client_context import bot_id

BOT2BOT_COMMANDS = {"bot2bot", "bot2botskipreview"}


def message_fingerprint(message):
    return sha256(
        (getattr(message, "text", None) or getattr(message, "caption", None) or "").encode()
    ).hexdigest()


async def bot_command_allowed(message, command_name: str) -> bool:
    sender = getattr(message, "from_user", None)
    if not sender or not getattr(sender, "is_bot", False) or sender.id == bot_id(message._client):
        return True

    if getattr(message, "_emilia_bot2bot_approved", False):
        return True

    if command_name.lower() in BOT2BOT_COMMANDS:
        return False

    chat = getattr(message, "chat", None)
    if not chat or chat.type == ChatType.PRIVATE:
        return False

    settings = await get_bot2bot_settings(chat.id)
    mode = settings["mode"]
    if mode == "off":
        return False

    if mode == "admin":
        if not await has_chat_permission(message._client, chat.id, sender.id):
            return False

    if settings["skip_review"]:
        message._emilia_bot2bot_approved = True
        return True

    token = secrets.token_urlsafe(12)
    prompt = await message.reply(
        tr(
            "bot2bot.bot_command_review_required_from",
            command_name=command_name,
            user_mention=sender.mention,
        ),
    )
    await add_pending_bot_command(
        token,
        chat.id,
        message.id,
        sender.id,
        client_type="pyrogram",
        command_name=command_name,
        client_bot_id=bot_id(message._client),
        review_message_id=prompt.id,
        source_hash=message_fingerprint(message),
    )
    await prompt.edit_reply_markup(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("bot2bot.approve"),
                        callback_data=f"b2b:ok:{token}",
                        style=ButtonStyle.SUCCESS,
                    ),
                    InlineKeyboardButton(
                        tr("bot2bot.reject"),
                        callback_data=f"b2b:no:{token}",
                        style=ButtonStyle.DANGER,
                    ),
                ]
            ]
        )
    )
    return False


async def execute_approved_bot_command(client, message, reviewer_id: int = None):
    message._emilia_bot2bot_approved = True
    if reviewer_id is not None:
        message._emilia_bot2bot_reviewer_id = reviewer_id
    dispatcher = getattr(client, "dispatcher", None)
    if dispatcher is None:
        return False

    for group in dispatcher.groups.values():
        for handler in group:
            if not isinstance(handler, MessageHandler):
                continue
            try:
                if not await handler.check(client, message):
                    continue
                if inspect.iscoroutinefunction(handler.callback):
                    await handler.callback(client, message)
                else:
                    await dispatcher.loop.run_in_executor(
                        client.executor,
                        handler.callback,
                        client,
                        message,
                    )
                return True
            except StopPropagation:
                # Handler explicitly ended propagation after handling the
                # message - this is success, not failure.
                return True
            except ContinuePropagation:
                # Handler wants the next matching handler to run instead.
                continue
            except Exception as exc:
                LOGGER.warning("Approved bot-to-bot command failed: %s", exc)
                return False
    return False
