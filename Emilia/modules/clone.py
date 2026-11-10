import asyncio
import os
import re
import time
from urllib.parse import urlparse

import aiohttp
from pymongo.errors import PyMongoError
from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.errors import (
    ChatWriteForbidden,
    MessageNotModified,
    RPCError,
    UserIsBlocked,
    UserNotParticipant,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, User

from Emilia.application import LOGGER, db, pgram
from Emilia.config import Config
from Emilia.custom_filter import auth, callbackquery, command, listen
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.services.clone_runtime import clone_manager
from Emilia.utils import http
from Emilia.utils.command_help import reply_usage
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.net_guard import is_safe_url
from Emilia.utils.tg_safe import flood_safe

clone_db = db.clone
startpic = db.startpic
clone_slots = db.clone_slots
clone_payments = db.clone_payments

# {owner_user_id: bot_id}
_PENDING_STARTPIC = {}

_STARTPIC_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


async def get_clone_info_by_bot_id(bot_id):
    return await clone_db.find_one({"_id": bot_id})


async def validate_token(token: str):
    try:
        # Check the token without creating a fresh MTProto authorization.
        response = await http.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=Config.CLONE_START_TIMEOUT,
            retries=1,
            public_only=False,
        )
        if response.status in {401, 404}:
            return False, "invalid", None
        if response.status != 200:
            return False, "network", None
        data = response.json()
        if not data.get("ok"):
            return False, "network", None
        me = data["result"]
        return True, "ok", User(
            id=me["id"],
            is_bot=me["is_bot"],
            first_name=me["first_name"],
            username=me.get("username"),
        )
    except (aiohttp.ClientError, OSError, ValueError, KeyError, TypeError) as exc:
        LOGGER.warning("Clone token validation failed: %s", type(exc).__name__)
        return False, "network", None


@auth(pattern="stats")
async def stats_(client, message):
    users = await db.users.count_documents({})
    chats = await db.chats.count_documents({})
    bots = await clone_db.count_documents({})
    active_clones = len(clone_manager.clones)

    await message.reply_text(
        tr(
            "clone.bot_statistics_chats_users_cloned_bots_database_active",
            chats=chats,
            users=users,
            bots=bots,
            active_clones=active_clones,
        )
    )


async def delete_clone_by_bot_id(bot_id: int, *, owner_id=None) -> bool:
    from Emilia.services.clones import delete_clone

    return await delete_clone(bot_id, owner_id=owner_id)


async def clone(owner_id, token, bot_id, *, restart=False):
    from Emilia.services.clones import register_clone

    result = await register_clone(owner_id, token, bot_id, validate_token, restart=restart)
    if result[0] == "invalid":
        doc = await clone_db.find_one_and_update(
            {
                "_id": bot_id,
                "owner_id": owner_id,
                "token": token,
                "status": {"$nin": ["dead", "deleting"]},
            },
            {"$set": {"status": "dead"}},
        )
        if doc:
            bot = f"@{doc['bot_username']}" if doc.get("bot_username") else str(bot_id)
            try:
                await pgram.send_message(
                    owner_id, tr("clone.invalid_token_retry_stopped", bot=bot)
                )
            except (RPCError, OSError) as exc:
                LOGGER.warning("Could not notify clone %s owner: %s", bot_id, type(exc).__name__)
    return result


async def clone_start_up():
    from Emilia.services.clones import recover_deletions

    await recover_deletions()
    sem = asyncio.Semaphore(Config.CLONE_START_CONCURRENCY)

    async def start_one(doc):
        if not doc.get("token") or not doc.get("owner_id"):
            return
        async with sem:
            await clone(doc["owner_id"], doc["token"], doc["_id"])

    batch = []
    async for doc in clone_db.find({"status": {"$nin": ["dead", "deleting"]}}):
        batch.append(start_one(doc))
        if len(batch) >= Config.CLONE_START_CONCURRENCY:
            await asyncio.gather(*batch)
            batch.clear()
    if batch:
        await asyncio.gather(*batch)


async def clone_health_loop():
    while True:
        await asyncio.sleep(Config.CLONE_HEALTH_INTERVAL)
        try:
            from Emilia.services.clones import recover_deletions

            await recover_deletions()
            async for doc in clone_db.find({"status": {"$nin": ["dead", "deleting"]}}):
                entry = clone_manager.clones.get(doc["_id"])
                if entry and entry["client"].is_connected:
                    continue
                await clone(doc["owner_id"], doc["token"], doc["_id"])
        except Exception:
            LOGGER.exception("Clone health check failed")


@command("clone", chat_scope="private", rate_limit=Config.RATE_LIMIT_HEAVY)
async def clone_bot(client, message):
    if getattr(client, "is_clone", False):
        return await message.reply_text(tr("clone.create_clones_through_the_main_bot"))
    parts = message.text.split(None, 1)
    if len(parts) < 2:
        return await reply_usage(message)
    token = parts[1].strip()
    try:
        await message.delete()
    except (RPCError, OSError):
        LOGGER.warning("Could not delete a submitted token message")
    if not re.fullmatch(r"[0-9]{5,15}:[A-Za-z0-9_-]{20,}", token):
        return await client.send_message(message.chat.id, tr("clone.invalid_bot_token"))
    bot_id = int(token.split(":", 1)[0])
    wait = await client.send_message(
        message.chat.id, tr("clone.validating_token_and_starting_your_clone")
    )
    result, username, _ = await clone(message.from_user.id, token, bot_id)
    if result == "success":
        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(tr("clone.manage_my_bots"), callback_data="mybots_list")],
                [
                    InlineKeyboardButton(
                        tr("clone.add_to_a_group"),
                        url=f"https://t.me/{username}?startgroup=true",
                    )
                ],
            ]
        )
        return await wait.edit_text(tr("clone.live", username=username), reply_markup=keyboard)
    errors = {
        "owned": tr("clone.bot_belongs_another_clone_owner"),
        "busy": tr("clone.clone_being_managed_another_instance_try_again_shortly"),
        "limit": tr("clone.clone_limit_has_reached_delete_existing_clone_unlock"),
        "invalid": tr("clone.telegram_rejected_token_generate_new_token_botfather"),
    }
    text = errors.get(result, tr("clone.clone_could_not_start_please_try_again"))
    keyboard = (
        InlineKeyboardMarkup(
            [[InlineKeyboardButton(tr("clone.unlock_another_slot"), callback_data="clonepay")]]
        )
        if result == "limit" and Config.CLONE_PREMIUM_ENABLED
        else None
    )
    await wait.edit_text(text, reply_markup=keyboard)


@command("deleteclone", chat_scope="private")
async def delete_cloned(client, message):
    if getattr(client, "is_clone", False):
        return await message.reply_text(tr("clone.this_feature_is_only_available_in_the"))

    user_id = message.from_user.id
    docs = await clone_db.find({"owner_id": user_id}).to_list(length=None)
    if not docs:
        return await message.reply_text(tr("clone.you_have_no_clones_create_one_with"))

    keyboard = [
        [
            InlineKeyboardButton(
                tr("clone.delete", bot_username=d.get("bot_username")),
                callback_data=f"delclone_{d['_id']}",
                style=ButtonStyle.DANGER,
            )
        ]
        for d in docs
    ]
    keyboard.append(
        [
            InlineKeyboardButton(
                tr("buttons.cancel"),
                callback_data="delclone_cancel",
                style=ButtonStyle.DANGER,
            )
        ]
    )
    await message.reply_text(
        tr("clone.select_the_clone_you_want_to_delete"),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


@callbackquery(
    pattern="delclone", access=CallbackAccess(user_id=lambda client, query: query.message.chat.id)
)
async def delclone_callback(client, query):
    if getattr(client, "is_clone", False):
        return await query.answer()
    if query.message.chat.type != ChatType.PRIVATE:
        return await query.answer(tr("clone.not_your_button"), show_alert=True)
    data = query.data
    if data == "delclone_cancel":
        return await query.message.edit_text(tr("clone.cancelled"))

    try:
        bot_id = int(data.split("_", 1)[1])
    except (ValueError, IndexError):
        return await query.answer(tr("clone.invalid_selection"), show_alert=True)

    doc = await clone_db.find_one({"_id": bot_id})
    if not doc or query.from_user.id != doc.get("owner_id"):
        return await query.answer(tr("clone.not_your_button"), show_alert=True)

    username = doc.get("bot_username")
    if not await delete_clone_by_bot_id(bot_id, owner_id=query.from_user.id):
        return await query.answer(tr("clone.invalid_selection"), show_alert=True)
    await query.message.edit_text(
        tr("clone.clone_deleted_bot_stopped_removed_from_our_servers", username=username)
    )


def render_mybots_list(docs):
    text = tr("clone.bots_tap_one_manage")
    keyboard = [
        [
            InlineKeyboardButton(
                tr("clone.render_mybots_list_bot_username", bot_username=d.get("bot_username")),
                callback_data=f"mybots_{d['_id']}",
            )
        ]
        for d in docs
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def render_bot_panel(bot_id):
    doc = await clone_db.find_one({"_id": bot_id})
    if not doc:
        return None, None
    username = doc.get("bot_username")
    name = doc.get("bot_name")
    if bot_id in clone_manager.clones:
        status = "Running"
    else:
        status = {
            "running": "Running",
            "stopped": "Stopped",
            "dead": tr("clone.dead_token_revoked"),
        }.get(doc.get("status"), "Stopped")
    users_count = await db.users.count_documents({"bot_ids": bot_id})
    chats_count = await db.chats.count_documents({"bot_ids": bot_id})
    text = tr(
        "clone.status_users_chats",
        username=username,
        name=name,
        status=status,
        users_count=users_count,
        chats_count=chats_count,
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("clone.restart"),
                    callback_data=f"cbot_restart_{bot_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    tr("buttons.delete"),
                    callback_data=f"cbot_del_{bot_id}",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("clone.start_pic"),
                    callback_data=f"cbot_pic_{bot_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    tr("clone.broadcast_help"),
                    callback_data=f"cbot_bc_{bot_id}",
                    style=ButtonStyle.PRIMARY,
                ),
            ],
            [InlineKeyboardButton(tr("clone.all_bots"), callback_data="mybots_list")],
        ]
    )
    return text, keyboard


@command("mybots", chat_scope="private")
async def mybots(client, message):
    if getattr(client, "is_clone", False):
        return await message.reply_text(tr("clone.this_feature_is_only_available_for_the"))

    docs = await clone_db.find({"owner_id": message.from_user.id}).to_list(length=None)
    if not docs:
        return await message.reply_text(tr("clone.you_have_no_bots_yet_create_one"))
    text, keyboard = render_mybots_list(docs)
    await message.reply_text(text, reply_markup=keyboard)


@callbackquery(
    pattern="mybots", access=CallbackAccess(user_id=lambda client, query: query.message.chat.id)
)
async def mybots_callback(client, query):
    if getattr(client, "is_clone", False):
        return await query.answer()
    if query.message.chat.type != ChatType.PRIVATE:
        return await query.answer(tr("clone.not_your_button"), show_alert=True)
    data = query.data
    if data == "mybots_list":
        docs = await clone_db.find({"owner_id": query.from_user.id}).to_list(length=None)
        if not docs:
            return await query.message.edit_text(tr("clone.you_have_no_bots_yet_create_one"))
        text, keyboard = render_mybots_list(docs)
        await query.message.edit_text(text, reply_markup=keyboard)
        return await query.answer()

    try:
        bot_id = int(data.split("_", 1)[1])
    except (ValueError, IndexError):
        return await query.answer(tr("clone.invalid_selection"), show_alert=True)

    doc = await clone_db.find_one({"_id": bot_id})
    if not doc or query.from_user.id != doc.get("owner_id"):
        return await query.answer(tr("clone.not_your_button"), show_alert=True)

    text, keyboard = await render_bot_panel(bot_id)
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@callbackquery(
    pattern="cbot", access=CallbackAccess(user_id=lambda client, query: query.message.chat.id)
)
async def cbot_callback(client, query):
    if getattr(client, "is_clone", False):
        return await query.answer()
    if query.message.chat.type != ChatType.PRIVATE:
        return await query.answer(tr("clone.not_your_button"), show_alert=True)
    parts = query.data.split("_")
    try:
        action = parts[1]
        bot_id = int(parts[2])
    except (ValueError, IndexError):
        return await query.answer(tr("clone.invalid_selection"), show_alert=True)

    doc = await clone_db.find_one({"_id": bot_id})
    if not doc or query.from_user.id != doc.get("owner_id"):
        return await query.answer(tr("clone.not_your_button"), show_alert=True)

    username = doc.get("bot_username")

    if action == "restart":
        await query.answer(tr("clone.restarting"))
        await clone(doc["owner_id"], doc["token"], bot_id, restart=True)
        text, keyboard = await render_bot_panel(bot_id)
        try:
            return await query.message.edit_text(text, reply_markup=keyboard)
        except MessageNotModified:
            pass

    if action == "del":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("buttons.yes"),
                        callback_data=f"delclone_{bot_id}",
                        style=ButtonStyle.SUCCESS,
                    ),
                    InlineKeyboardButton(
                        tr("buttons.back"),
                        callback_data=f"mybots_{bot_id}",
                        style=ButtonStyle.PRIMARY,
                    ),
                ]
            ]
        )
        await query.message.edit_text(
            tr("clone.delete_stops_bot_permanently", username=username),
            reply_markup=keyboard,
        )
        return await query.answer()

    if action == "pic":
        now = time.monotonic()
        for user, (_, expiry) in tuple(_PENDING_STARTPIC.items()):
            if expiry <= now:
                _PENDING_STARTPIC.pop(user, None)
        _PENDING_STARTPIC[query.from_user.id] = (bot_id, now + 900)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("buttons.cancel"),
                        callback_data=f"cbot_piccancel_{bot_id}",
                        style=ButtonStyle.DANGER,
                    )
                ]
            ]
        )
        await query.message.edit_text(
            tr(
                "clone.send_photo_image_url_now_ll_set_s_start_picture_send_cancel_abort",
                username=username,
            ),
            reply_markup=keyboard,
        )
        return await query.answer()

    if action == "piccancel":
        _PENDING_STARTPIC.pop(query.from_user.id, None)
        text, keyboard = await render_bot_panel(bot_id)
        await query.message.edit_text(text, reply_markup=keyboard)
        return await query.answer(tr("clone.cancelled"))

    if action == "bc":
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("buttons.back"),
                        callback_data=f"mybots_{bot_id}",
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            ]
        )
        await query.message.edit_text(
            tr("clone.send_broadcast_chat_replying_message_want_send_modes", username=username),
            reply_markup=keyboard,
        )
        return await query.answer()

    await query.answer()


@command("setstartpic")
async def set_startpic(client, message):
    if not getattr(client, "is_clone", False):
        return await message.reply_text(tr("clone.this_feature_is_only_available_in_cloned"))

    me = client.me or await client.get_me()
    clone_info = await get_clone_info_by_bot_id(me.id)

    if not clone_info or message.from_user.id != clone_info.get("owner_id"):
        return await message.reply_text(tr("clone.you_are_not_authorized_to_set_the"))

    reply_message = message.reply_to_message
    if reply_message and reply_message.photo:
        await _save_clone_startpic(
            me.id, clone_info["owner_id"], "file_id", reply_message.photo.file_id
        )
        await message.reply_text(tr("clone.start_picture_updated_successfully_the_new_start"))
    else:
        args = message.text.split(None, 1)
        if len(args) < 2:
            return await reply_usage(message)

        url = args[1]
        path = urlparse(url).path.lower()
        if not path.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return await message.reply_text(tr("clone.the_url_you_provided_is_not_an"))
        if not await asyncio.to_thread(is_safe_url, url):
            return await message.reply_text(tr("clone.that_url_isn_t_allowed_use_a"))

        await _save_clone_startpic(me.id, clone_info["owner_id"], "url", url)
        await message.reply_text(tr("clone.start_picture_preview_updated", url=url))


async def _save_clone_startpic(bot_id, owner_id, field, value):
    from Emilia.services.clones import _mutation_lock

    if field not in {"url", "file_id"}:
        raise ValueError("Invalid start picture type")
    async with clone_manager.bot_lock(bot_id), _mutation_lock(bot_id) as claimed:
        doc = (
            await clone_db.find_one(
                {"_id": bot_id, "owner_id": owner_id, "status": {"$ne": "deleting"}}
            )
            if claimed
            else None
        )
        if not doc:
            raise ValueError("Clone ownership changed or another operation is in progress")
        await atomic_upsert(
            startpic,
            {"bot_id": bot_id},
            {
                "$set": {field: value, "user_id": owner_id},
                "$unset": {"url" if field == "file_id" else "file_id": "", "token": ""},
            },
        )


@listen(filters=filters.private & filters.incoming)
async def startpic_conversation(client, message):
    if getattr(client, "is_clone", False):
        return
    user_id = message.from_user.id if message.from_user else None
    if user_id not in _PENDING_STARTPIC:
        return

    text = (message.text or message.caption or "").strip()
    if text.lower() in ("/cancel", "cancel"):
        _PENDING_STARTPIC.pop(user_id, None)
        return await message.reply_text(tr("clone.cancelled"))

    bot_id, expiry = _PENDING_STARTPIC[user_id]
    if expiry <= time.monotonic():
        _PENDING_STARTPIC.pop(user_id, None)
        return
    if not await clone_db.find_one(
        {"_id": bot_id, "owner_id": user_id, "status": {"$ne": "deleting"}}
    ):
        _PENDING_STARTPIC.pop(user_id, None)
        return await message.reply_text(tr("clone.not_your_button"))

    if message.photo:
        if bot_id not in clone_manager.clones:
            _PENDING_STARTPIC.pop(user_id, None)
            return await message.reply_text(tr("clone.that_clone_isn_t_running_right_now"))
        file_size = getattr(message.photo, "file_size", 0) or 0
        if file_size > _STARTPIC_MAX_BYTES:
            _PENDING_STARTPIC.pop(user_id, None)
            return await message.reply_text(
                tr(
                    "clone.image_too_large_max_mb_send_smaller_photo",
                    startpic_max_bytes=_STARTPIC_MAX_BYTES // (1024 * 1024),
                )
            )

        clone_client = clone_manager.clones[bot_id]["client"]
        username = clone_manager.clones[bot_id].get("bot_username", "")
        path = None
        try:
            path = await client.download_media(message.photo.file_id, in_memory=False)
            sent = await clone_client.send_photo(user_id, path)
            await _save_clone_startpic(bot_id, user_id, "file_id", sent.photo.file_id)
            try:
                await sent.delete()
            except (RPCError, OSError):
                pass
        except (RPCError, PyMongoError, OSError) as e:
            LOGGER.error(f"startpic photo transfer failed for {bot_id}: {e}")
            _PENDING_STARTPIC.pop(user_id, None)
            return await message.reply_text(
                tr("clone.couldn_t_set_that_photo_make_sure", username=username)
            )
        finally:
            if path:
                try:
                    os.remove(path)
                except OSError:
                    pass
        _PENDING_STARTPIC.pop(user_id, None)
        return await message.reply_text(tr("clone.start_picture_updated_it_s_live_on"))

    if message.document or message.video or message.animation or message.sticker:
        return await message.reply_text(tr("clone.please_send_the_image_as_a_photo"))

    if text:
        url = text.split()[0]
        path = urlparse(url).path.lower()
        if not path.endswith((".jpg", ".jpeg", ".png", ".webp")):
            return await message.reply_text(tr("clone.that_doesn_t_look_like_an_image"))
        if not await asyncio.to_thread(is_safe_url, url):
            return await message.reply_text(
                tr("clone.url_isn_t_allowed_use_public_http_s_image_url_cancel")
            )
        await _save_clone_startpic(bot_id, user_id, "url", url)
        _PENDING_STARTPIC.pop(user_id, None)
        return await message.reply_text(tr("clone.start_picture_updated_it_s_live_on"))

    return await message.reply_text(tr("clone.send_a_photo_or_an_image_url"))


@command("broadcast")
async def broadcast(client, message):
    if not getattr(client, "is_clone", False):
        return await message.reply_text(tr("clone.broadcast_is_only_available_on_cloned_bots"))

    if not message.reply_to_message:
        return await reply_usage(message)

    me = client.me or await client.get_me()
    bot_id = me.id
    clone_info = await get_clone_info_by_bot_id(bot_id)

    if not clone_info or message.from_user.id != clone_info.get("owner_id"):
        return await message.reply_text(tr("clone.you_are_not_authorized_to_use_this"))

    args = message.text.split(None, 1)
    if len(args) < 2 or args[1].lower() not in ["-all", "-users", "-chats"]:
        user_count = await db.users.count_documents({"bot_ids": bot_id})
        chat_count = await db.chats.count_documents({"bot_ids": bot_id})
        return await message.reply_text(
            tr(
                "clone.please_provide_a_mode_broadcast_all_broadcast",
                user_count=user_count,
                chat_count=chat_count,
            )
        )

    mode = args[1].lower()
    reply = message.reply_to_message

    if mode == "-all":
        n = await db.users.count_documents({"bot_ids": bot_id}) + await db.chats.count_documents(
            {"bot_ids": bot_id}
        )
    elif mode == "-users":
        n = await db.users.count_documents({"bot_ids": bot_id})
    else:
        n = await db.chats.count_documents({"bot_ids": bot_id})

    wait = await message.reply_text(tr("clone.broadcasting_targets_may_take_while", broadcasting=n))

    try:
        if mode == "-all":
            us, uf = await broadcast_to_users(bot_id, reply, wait)
            cs, cf = await broadcast_to_chats(bot_id, reply, wait)
            await wait.edit_text(
                tr(
                    "clone.broadcast_complete_users_success_failed_chats_success_failed",
                    users_sent=us,
                    users_failed=uf,
                    chats_sent=cs,
                    chats_failed=cf,
                )
            )
        elif mode == "-users":
            s, f = await broadcast_to_users(bot_id, reply, wait)
            await wait.edit_text(
                tr(
                    "clone.user_broadcast_complete_users_success_failed",
                    users_sent=s,
                    users_failed=f,
                )
            )
        else:
            s, f = await broadcast_to_chats(bot_id, reply, wait)
            await wait.edit_text(
                tr(
                    "clone.chat_broadcast_complete_chats_success_failed",
                    chats_sent=s,
                    chats_failed=f,
                )
            )
    except (RPCError, PyMongoError, OSError):
        LOGGER.exception("Broadcast failed")
        await wait.edit_text(tr("clone.broadcast_failed"))


async def broadcast_to_users(bot_id, message, wait):
    cursor = db.users.find({"bot_ids": bot_id}, {"user_id": 1})
    success, failed = 0, 0

    async for doc in cursor:
        uid = doc["user_id"]
        try:
            await flood_safe(lambda uid=uid: message.copy(uid))
            success += 1
            await asyncio.sleep(0.05)
        except UserIsBlocked:
            await db.users.update_one({"user_id": uid}, {"$pull": {"bot_ids": bot_id}})
            failed += 1
        except (RPCError, OSError):
            failed += 1

        if (success + failed) % 200 == 0:
            chat_id = wait.chat.id
            client = wait._client
            try:
                await wait.delete()
            except (RPCError, OSError):
                pass
            try:
                wait = await client.send_message(
                    chat_id, tr("clone.broadcasting_done", success=success + failed)
                )
            except (RPCError, OSError):
                pass

    return success, failed


async def broadcast_to_chats(bot_id, message, wait):
    cursor = db.chats.find({"bot_ids": bot_id}, {"chat_id": 1})
    success, failed = 0, 0

    async for doc in cursor:
        cid = doc["chat_id"]
        try:
            await flood_safe(lambda cid=cid: message.copy(cid))
            success += 1
            await asyncio.sleep(0.05)
        except (ChatWriteForbidden, UserNotParticipant):
            await db.chats.update_one({"chat_id": cid}, {"$pull": {"bot_ids": bot_id}})
            failed += 1
        except (RPCError, OSError):
            failed += 1

        if (success + failed) % 200 == 0:
            chat_id = wait.chat.id
            client = wait._client
            try:
                await wait.delete()
            except (RPCError, OSError):
                pass
            try:
                wait = await client.send_message(
                    chat_id, tr("clone.broadcasting_done", success=success + failed)
                )
            except (RPCError, OSError):
                pass

    return success, failed


@command("clonestats")
async def clone_stats(client, message):
    if not getattr(client, "is_clone", False):
        return await message.reply_text(tr("clone.use_this_command_in_your_cloned_bot"))
    me = client.me or await client.get_me()
    clone_info = await get_clone_info_by_bot_id(me.id)
    if not clone_info or message.from_user.id != clone_info.get("owner_id"):
        return await message.reply_text(tr("clone.only_the_clone_owner_can_use_this"))
    users = await db.users.count_documents({"bot_ids": me.id})
    chats = await db.chats.count_documents({"bot_ids": me.id})
    await message.reply_text(
        tr("clone.stats_users_chats", bot_username=me.username, users=users, chats=chats)
    )


@auth(pattern="clonestatus")
async def clone_status(client, message):
    if not clone_manager.clones:
        return await message.reply_text(tr("clone.no_active_clone_clients_running"))

    status_msg = tr("clone.active_clone_clients_status")
    for bot_id, info in clone_manager.clones.items():
        status_msg += tr("clone.bot_id", bot_id=bot_id)
        status_msg += (
            f"**Bot**: @{info.get('bot_username', 'Unknown')} ({info.get('bot_name', 'Unknown')})\n"
        )
        status_msg += f"**Owner**: `{info.get('owner_id', 'Unknown')}`\n"
        status_msg += tr("clone.status_online")

    status_msg += tr("clone.total_active_clones", clones=len(clone_manager.clones))
    await message.reply_text(status_msg)


@callbackquery(pattern="clonepay", access=CallbackAccess(public=True))
async def clone_pay_callback(client, query):
    if getattr(client, "is_clone", False) or not Config.CLONE_PREMIUM_ENABLED:
        return await query.answer(tr("clone.extra_slots_are_unavailable"), show_alert=True)
    from Emilia.services.clone_payments import create_invoice

    payload = await create_invoice(query.from_user.id, Config.CLONE_PREMIUM_STARS)
    await client.send_invoice(
        chat_id=query.from_user.id,
        title=tr("clone.extra_clone_slot"),
        description=tr("clone.unlock_one_additional_clone_slot"),
        payload=payload,
        currency="XTR",
        prices=[LabeledPrice(label="1 slot", amount=Config.CLONE_PREMIUM_STARS)],
    )
    await query.answer()


@Client.on_pre_checkout_query()
async def clone_pre_checkout(client, pre_checkout_query):
    if getattr(client, "is_clone", False):
        return
    from Emilia.services.clone_payments import validate_invoice

    valid = Config.CLONE_PREMIUM_ENABLED and await validate_invoice(
        pre_checkout_query.invoice_payload,
        pre_checkout_query.from_user.id,
        pre_checkout_query.currency,
        pre_checkout_query.total_amount,
        checkout=True,
    )
    await pre_checkout_query.answer(
        ok=bool(valid),
        error_message=None if valid else tr("clone.invoice_invalid_expired_request_new_one"),
    )


@Client.on_message(filters.successful_payment)
async def clone_successful_payment(client, message):
    if getattr(client, "is_clone", False):
        return
    from Emilia.services.clone_payments import grant_slot, refund_invalid_payment, validate_invoice

    payment = message.successful_payment
    user_id = message.from_user.id
    receipt = await clone_payments.find_one({"_id": payment.telegram_payment_charge_id})
    if payment.currency != "XTR":
        return await message.reply_text(tr("clone.payment_received_but_the_invoice_could_not"))
    valid = receipt is not None or await validate_invoice(
        payment.invoice_payload, user_id, payment.currency, payment.total_amount
    )
    if not valid or (receipt and receipt.get("refund_pending")):
        try:
            await refund_invalid_payment(
                user_id,
                payment.telegram_payment_charge_id,
                payment.total_amount,
                payment.invoice_payload,
                client,
            )
        except Exception:
            LOGGER.exception("Rejected invoice refund is pending")
            return await message.reply_text(tr("clone.invalid_invoice_refund_pending"))
        return await message.reply_text(tr("clone.invalid_invoice_refunded"))
    try:
        added = await grant_slot(
            user_id,
            payment.telegram_payment_charge_id,
            payment.total_amount,
            payment.invoice_payload,
        )
    except Exception:
        LOGGER.exception("Payment grant failed")
        return await message.reply_text(tr("clone.payment_received_the_slot_grant_is_pending"))
    if added:
        await message.reply_text(tr("clone.payment_received_one_extra_clone_slot_unlocked"))


@auth(pattern="refundstar")
async def refund_star(client, message):
    if getattr(client, "is_clone", False):
        return
    from Emilia.services.clone_payments import refund_slot

    parts = message.text.split()
    if len(parts) != 2:
        return await reply_usage(message)
    try:
        refunded = await refund_slot(parts[1], client)
    except Exception:
        LOGGER.exception("Payment refund failed")
        return await message.reply_text(tr("clone.refund_failed_check_the_operator_logs"))
    await message.reply_text(
        tr("clone.payment_refunded_slot_removed")
        if refunded
        else tr("clone.payment_already_refunded")
    )


@auth(pattern="clonepayments")
async def clone_payments_list(client, message):
    if getattr(client, "is_clone", False):
        return
    docs = await clone_payments.find({}).sort("created_at", -1).to_list(length=20)
    if not docs:
        return await message.reply_text(tr("clone.no_clone_payments_recorded"))
    lines = [tr("clone.recent_clone_payments")]
    for d in docs:
        flag = " (refunded)" if d.get("refunded") else ""
        lines.append(f"`{d['_id']}` - user `{d['user_id']}`, {d.get('stars')}*{flag}")
    await message.reply_text("\n".join(lines))


async def shutdown_all_clones():
    from Emilia.services.clones import shutdown_clones

    await shutdown_clones()
