import aiohttp
from pymongo.errors import PyMongoError
from pyrogram import Client, filters
from pyrogram.errors import PeerIdInvalid, RPCError, UserIsBlocked
from pyrogram.types import (
    CallbackQuery,
    ChatJoinRequest,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from redis.exceptions import RedisError

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command
from Emilia.database.autoapprove import cache, get_autoapprove_mode, set_autoapprove_mode
from Emilia.database.federations import get_chat_fed, get_fban_user
from Emilia.database.welcome import GetCaptchaSettings, isRuleCaptcha
from Emilia.locales import tr
from Emilia.modules.greetings.captcha.captcharules_button import ruleCaptchaButton
from Emilia.modules.greetings.captcha.text_captcha import dispatch_text_math_captcha
from Emilia.services import captcha
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import bot_has_permission, user_has_permission
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.http import get
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_id, actor_name


@command("autoapprove", chat_scope="supergroup_or_channel", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def autoapprove_cmd(client, message):
    chat_id = effective_chat_id(message)

    if not await bot_has_permission(
        message, chat_id=chat_id, privileges="can_invite_users", fresh=True, silent=False
    ):
        return

    if not await user_has_permission(
        message, chat_id=chat_id, privileges="can_restrict_members", fresh=True, silent=False
    ):
        return

    args = message.text.split()
    if len(args) == 1:
        current_mode = await get_autoapprove_mode(chat_id)
        return await message.reply(
            tr("autoapprove.current_autoapprove_mode", current_mode=current_mode)
        )

    mode = args[1].lower()
    valid_modes = ["off", "on", "antispam", "rules", "captcha"]

    if mode not in valid_modes:
        return await message.reply(
            tr(
                "autoapprove.invalid_mode_valid_modes",
                mode=mode,
                valid_modes="`, `".join(valid_modes),
            )
        )

    await set_autoapprove_mode(chat_id, mode)
    await message.reply(tr("autoapprove.successfully_set_autoapprove_mode", mode=mode))

    # Return standard event tuple for logging
    return ("AUTOAPPROVE", actor_id(message), actor_name(message))


async def check_cas(user_id: int) -> bool | None:
    """Return the CAS ban status, or None when it cannot be verified."""

    async def load():
        response = await get(
            "https://api.cas.chat/check",
            params={"user_id": user_id},
            headers={"Authorization": f"Bearer {Config.CAS_API_KEY}"},
            max_redirects=0,
            timeout=3,
            retries=1,
            max_bytes=65536,
        )
        if response.status not in {200, 404}:
            response.raise_for_status()
            raise ValueError("Unexpected CAS response status")
        data = response.json()
        if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
            raise ValueError("Invalid CAS response")
        result = data.get("result")
        if response.status == 200 and data["ok"] and isinstance(result, dict) and result:
            return True
        if not data["ok"] and (
            data.get("error_code") == 404
            or (
                data.get("error_code") is None
                and str(data.get("description", "")).rstrip(".").casefold() == "record not found"
            )
        ):
            return False
        raise ValueError("CAS did not return a verified ban status")

    try:
        return await cache.get_or_load(f"cas_{user_id}", load, ttl=300)
    except (aiohttp.ClientError, TimeoutError, ValueError) as e:
        LOGGER.error(f"CAS Check Error: {e}")
        return None


@Client.on_chat_join_request(filters.group | filters.channel)
async def autoapprove_handler(client: Client, request: ChatJoinRequest):
    chat_id = request.chat.id
    user_id = request.from_user.id
    mode = await get_autoapprove_mode(chat_id)

    if mode == "off":
        return

    # Anti-spam hook (Runs for antispam, rules, and captcha modes)
    if mode in ["antispam", "rules", "captcha"]:
        # Check FedBans
        fed_id = await get_chat_fed(chat_id)
        if fed_id:
            is_fed_banned, _, _ = await get_fban_user(fed_id, str(user_id))
            if is_fed_banned:
                try:
                    await client.decline_chat_join_request(chat_id, user_id)
                except (RPCError, OSError):
                    pass
                return

        # Check CAS
        is_cas_banned = await check_cas(user_id)
        if is_cas_banned is None:
            return
        if is_cas_banned:
            try:
                await client.decline_chat_join_request(chat_id, user_id)
            except (RPCError, OSError):
                pass
            return

    # Mode: antispam / on -> Approve immediately
    if mode in ["on", "antispam"]:
        try:
            await client.approve_chat_join_request(chat_id, user_id)
        except (RPCError, OSError) as e:
            LOGGER.error(f"Failed to approve join request: {e}")
        return

    if mode not in {"captcha", "rules"}:
        return
    captcha_mode, captcha_text, _ = await GetCaptchaSettings(chat_id)
    challenge = await captcha.begin(
        client,
        chat_id,
        user_id,
        "rules" if mode == "rules" else captcha_mode,
        source="join_request",
        rules=mode == "rules" or await isRuleCaptcha(chat_id),
        private_chat_id=getattr(request, "user_chat_id", None) or user_id,
        chat_title=request.chat.title,
    )
    try:
        if mode == "rules":
            await ruleCaptchaButton(client, request, chat_id, 0, challenge=challenge)
        elif captcha_mode in {"text", "math"}:
            await dispatch_text_math_captcha(
                client,
                user_id,
                chat_id,
                captcha_mode,
                challenge=challenge,
                caption=tr(
                    "autoapprove.join_please_solve_captcha_below_prove_human",
                    chat_title=request.chat.title,
                ),
            )
        else:
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton(captcha_text, callback_data=f"cjrcap_{challenge['token']}")]]
            )
            sent = await client.send_message(
                challenge["private_chat_id"],
                text=tr(
                    "autoapprove.hello_join_please_prove_human_clicking_button_below",
                    user_name=request.from_user.first_name,
                    chat_title=request.chat.title,
                ),
                reply_markup=keyboard,
            )
            if not await captcha.bind_prompt(challenge, sent):
                await sent.delete()
    except (UserIsBlocked, PeerIdInvalid):
        await captcha.remove(challenge)
    except Exception as e:
        await captcha.remove(challenge)
        LOGGER.error("Failed to send join-request verification: %s", e)


async def _complete_join_request(client, query, stages, success_key):
    challenge = await captcha.from_callback(client, query, query.data[7:], stages)
    if not challenge:
        return
    if challenge["source"] != "join_request":
        return await query.answer(tr("custom_filter.this_button_has_expired"), show_alert=True)
    try:
        if challenge["stage"] == "button" and challenge["rules"]:
            await query.answer()
            if await ruleCaptchaButton(client, query, challenge["chat_id"], 0, challenge=challenge):
                await query.message.edit_text(tr("captcha.accept_rules_prompt"), reply_markup=None)
            return
        if not await captcha.complete(client, challenge):
            return await query.answer(tr("captcha.processing"))
        await query.answer(tr(success_key))
        try:
            if query.message.document:
                await query.message.edit_caption(tr(success_key), reply_markup=None)
            else:
                await query.message.edit_text(tr(success_key), reply_markup=None)
        except RPCError:
            pass
    except (RPCError, PyMongoError, RedisError, OSError) as e:
        await query.answer(tr("autoapprove.failed_to_approve_you_might_have_been"), show_alert=True)
        LOGGER.error("Join-request verification failed: %s", e)


@callbackquery(
    filters=filters.regex("^cjrcap_[A-Za-z0-9_-]{16}$"), access=CallbackAccess(public=True)
)
async def autoapprove_captcha_callback(client: Client, query: CallbackQuery):
    await _complete_join_request(
        client, query, {"button"}, "autoapprove.captcha_passed_you_have_been_approved_to"
    )


@callbackquery(
    filters=filters.regex("^cjrrul_[A-Za-z0-9_-]{16}$"), access=CallbackAccess(public=True)
)
async def autoapprove_rules_callback(client: Client, query: CallbackQuery):
    await _complete_join_request(
        client, query, {"rules"}, "autoapprove.thank_you_for_agreeing_to_the_rules"
    )
