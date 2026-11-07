import asyncio
import io
import logging
import re

from aiohttp import ClientError
from bson import ObjectId
from pymongo.errors import PyMongoError
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultCachedDocument,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedSticker,
    InputTextMessageContent,
    MessageOriginChannel,
    MessageOriginChat,
    MessageOriginHiddenUser,
    MessageOriginImport,
    MessageOriginUser,
)
from webcolors import name_to_hex

from Emilia.application import db
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command, inlinequery
from Emilia.database import quotes as storage
from Emilia.locales import tr
from Emilia.utils.chat_status import check_user
from Emilia.utils.client_context import bot_id
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.http import post
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import message_actor

LOGGER = logging.getLogger(__name__)


def quote_sender(message):
    origin = message.forward_origin
    if isinstance(origin, (MessageOriginHiddenUser, MessageOriginImport)):
        return {"id": 0, "name": origin.sender_user_name, "username": "", "type": "private"}
    user = origin.sender_user if isinstance(origin, MessageOriginUser) else None
    chat = (
        origin.sender_chat
        if isinstance(origin, MessageOriginChat)
        else origin.chat
        if isinstance(origin, MessageOriginChannel)
        else None
    )
    chat = chat or message.sender_chat
    if chat:
        return {
            "id": chat.id,
            "name": chat.title,
            "username": chat.username,
            "type": chat.type.value,
        }
    user = user or message.from_user
    if user:
        return {
            "id": user.id,
            "name": " ".join(part for part in (user.first_name, user.last_name) if part),
            "username": user.username,
            "type": "private",
        }
    return {"id": 0, "name": tr("quotes.anonymous_sender"), "username": "", "type": "private"}


def quote_entities(message):
    result = []
    for entity in message.entities or message.caption_entities or []:
        item = {"type": entity.type.name.lower(), "offset": entity.offset, "length": entity.length}
        if entity.url:
            item["url"] = entity.url
        if entity.user:
            item["user"] = {"id": entity.user.id}
        if entity.custom_emoji_id:
            item["custom_emoji_id"] = str(entity.custom_emoji_id)
        if entity.language:
            item["language"] = entity.language
        result.append(item)
    return result


def _options(arguments: str):
    count, color = 1, "#1b1429"
    words = arguments.split()
    for word in words:
        if word.isascii() and word.isdigit():
            count = min(25, max(1, int(word)))
        elif re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})", word):
            color = word
        else:
            try:
                color = name_to_hex(word.lower())
            except ValueError:
                pass
    return count, color, "p" in words, "r" in words


async def _payload(client, messages, include_reply: bool):
    result = []
    previous_sender = None
    for message in messages:
        sender = quote_sender(message)
        item = {
            "chatId": sender["id"],
            "from": sender,
            "avatar": bool(sender["id"] and sender["id"] != previous_sender),
            "text": message.text or message.caption or "",
            "entities": quote_entities(message),
        }
        previous_sender = sender["id"]
        if include_reply and len(messages) == 1 and message.reply_to_message_id:
            reply = message.reply_to_message or await client.get_messages(
                message.chat.id, message.reply_to_message_id
            )
            if reply and not reply.empty:
                reply_sender = quote_sender(reply)
                item["replyMessage"] = {
                    "chatId": reply_sender["id"],
                    "from": reply_sender,
                    "name": reply_sender["name"],
                    "text": reply.text or reply.caption or "",
                    "entities": quote_entities(reply),
                }
        media = message.sticker or message.photo
        if media:
            item["mediaType"] = "sticker" if message.sticker else "photo"
            item["media"] = [
                {
                    "file_id": media.file_id,
                    "file_size": media.file_size,
                    "height": media.height,
                    "width": media.width,
                }
            ]
        elif message.voice:
            item["mediaType"] = "voice"
            item["voice"] = {"waveform": list(message.voice.waveform or [])}
        result.append(item)
    return result


def _rate_buttons(quote_id, up: int = 0, down: int = 0):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("quotes.upvote_count", count=up or ""), callback_data=f"qvote:{quote_id}:1"
                ),
                InlineKeyboardButton(
                    tr("quotes.downvote_count", count=down or ""),
                    callback_data=f"qvote:{quote_id}:-1",
                ),
            ]
        ]
    )


@command("q")
async def generate_quote(client, message):
    if not message.reply_to_message_id:
        return await message.reply_text(tr("quotes.reply_required"))
    arguments = message.text.split(maxsplit=1)
    count, color, image, include_reply = _options(arguments[1] if len(arguments) > 1 else "")
    try:
        messages = await client.get_messages(
            message.chat.id,
            list(range(message.reply_to_message_id, message.reply_to_message_id + count)),
        )
        messages = [item for item in messages if item and not item.empty]
        if not messages:
            return await message.reply_text(tr("quotes.reply_required"))
        extension = "png" if image else "webp"
        response = await post(
            f"{Config.QUOTE_API_URL.rstrip('/')}/generate.{extension}",
            public_only=False,
            timeout=60,
            json={
                "type": "quote",
                "backgroundColor": color,
                "width": 512,
                "height": 768,
                "scale": 3,
                "messages": await _payload(client, messages, include_reply),
                "botToken": client.bot_token,
            },
        )
        response.raise_for_status()
        expected = "image/png" if image else "image/webp"
        if (
            response.headers.get("Content-Type", "").split(";", 1)[0] != expected
            or not response.content
        ):
            raise ValueError("Quote API did not return the requested image format")
        with io.BytesIO(response.content) as stream:
            stream.name = f"quote.{extension}"
            sent = await (
                message.reply_document(stream) if image else message.reply_sticker(stream)
            )
        if not sent:
            return
        media = sent.document if image else sent.sticker
        quote = await storage.save_quote(db, message.chat.id, bot_id(client), media.file_id)
        if await storage.rating_enabled(db, message.chat.id):
            await sent.edit_reply_markup(
                _rate_buttons(quote["_id"], quote["up_count"], quote["down_count"])
            )
    except (ClientError, RPCError, PyMongoError, OSError, ValueError):
        LOGGER.exception("Quote generation failed")
        await message.reply_text(tr("quotes.generation_failed"))


@command("qrate", chat_scope="group")
@anonadmin_checker
async def quote_rating(client, message):
    actor, _ = message_actor(message)
    if actor is None or not await check_user(message, user_id=actor, privileges="can_change_info"):
        return
    arguments = message.text.split(maxsplit=1)
    if len(arguments) == 1:
        key = (
            "quotes.rating_on"
            if await storage.rating_enabled(db, message.chat.id)
            else "quotes.rating_off"
        )
        return await message.reply_text(tr(key))
    value = arguments[1].strip().lower()
    if value not in {"true", "yes", "on", "y", "false", "no", "off", "n"}:
        return await message.reply_text(tr("errors.invalid_toggle"))
    enabled = value in {"true", "yes", "on", "y"}
    await storage.set_rating(db, message.chat.id, enabled)
    await message.reply_text(tr("quotes.rating_enabled" if enabled else "quotes.rating_disabled"))


async def _is_member(client, chat_id: int, user_id: int) -> bool:
    if not -(2**63) < chat_id < 0:
        return False
    try:
        member = await asyncio.wait_for(client.get_chat_member(chat_id, user_id), timeout=10)
    except RPCError:
        return False
    return member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED} and (
        member.status != ChatMemberStatus.RESTRICTED or member.is_member
    )


@callbackquery(pattern=r"^qvote:([0-9a-f]{24}):(-?1)$", access=CallbackAccess(public=True))
async def quote_vote(client, query):
    quote_id = ObjectId(query.matches[0].group(1))
    choice = int(query.matches[0].group(2))
    current_bot = bot_id(client)
    chat_id = query.message.chat.id
    if not await _is_member(client, chat_id, query.from_user.id):
        return await query.answer(tr("quotes.members_only"), show_alert=True)
    if not await storage.rating_enabled(db, chat_id):
        return await query.answer(tr("quotes.rating_off"), show_alert=True)
    result = await storage.vote(db, quote_id, chat_id, current_bot, query.from_user.id, choice)
    if result is None:
        return await query.answer(tr("quotes.vote_unavailable"), show_alert=True)
    await query.edit_message_reply_markup(
        _rate_buttons(quote_id, result["up_count"], result["down_count"])
    )
    key = (
        "quotes.vote_removed"
        if not result["choice"]
        else "quotes.upvoted"
        if choice == 1
        else "quotes.downvoted"
    )
    await query.answer(tr(key))


@command("qtop", chat_scope="group")
async def show_top_quotes(client, message):
    await message.reply_text(
        tr("quotes.top_group_quotes"),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("quotes.open_top"),
                        switch_inline_query_current_chat=f"top:{message.chat.id}",
                    )
                ]
            ]
        ),
    )


@inlinequery(pattern=r"^top:(-?\d+)$")
async def top_quote_results(client, query):
    chat_id = int(query.matches[0].group(1))
    if not await _is_member(client, chat_id, query.from_user.id):
        result = InlineQueryResultArticle(
            title=tr("quotes.members_only"),
            input_message_content=InputTextMessageContent(tr("quotes.members_only")),
        )
        return await query.answer([result], cache_time=0, is_personal=True)
    offset = min(int(query.offset) if query.offset.isdigit() else 0, 10000)
    quotes = await storage.top_quotes(db, chat_id, bot_id(client), offset)
    rated = await storage.rating_enabled(db, chat_id)
    results = []
    for quote in quotes:
        markup = (
            _rate_buttons(quote["_id"], quote["up_count"], quote["down_count"]) if rated else None
        )
        arguments = {"id": str(quote["_id"]), "reply_markup": markup}
        if quote["kind"] == "sticker":
            result = InlineQueryResultCachedSticker(sticker_file_id=quote["file_id"], **arguments)
        elif quote["kind"] == "photo":
            result = InlineQueryResultCachedPhoto(photo_file_id=quote["file_id"], **arguments)
        else:
            result = InlineQueryResultCachedDocument(
                title=tr("quotes.title"), document_file_id=quote["file_id"], **arguments
            )
        results.append(result)
    await query.answer(
        results,
        is_gallery=True,
        cache_time=0,
        is_personal=True,
        next_offset=str(offset + 50) if len(quotes) == 50 and offset < 10000 else "",
    )


@command("qrand", chat_scope="group")
async def send_random_quote(client, message):
    quote = await storage.random_quote(db, message.chat.id, bot_id(client))
    if quote is None:
        return await message.reply_text(tr("quotes.empty"))
    markup = (
        _rate_buttons(quote["_id"], quote["up_count"], quote["down_count"])
        if await storage.rating_enabled(db, message.chat.id)
        else None
    )
    send = {
        "sticker": message.reply_sticker,
        "photo": message.reply_photo,
        "document": message.reply_document,
    }[quote["kind"]]
    await send(quote["file_id"], reply_markup=markup)
