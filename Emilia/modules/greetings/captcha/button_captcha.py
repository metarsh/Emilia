from pyrogram import Client, filters
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, InlineKeyboardButton

from Emilia.custom_filter import callbackquery
from Emilia.database.welcome import GetCaptchaSettings
from Emilia.locales import tr
from Emilia.modules.greetings.captcha.captcharules_button import ruleCaptchaButton
from Emilia.services import captcha
from Emilia.utils.client_context import bot_username
from Emilia.utils.menu_guard import CallbackAccess


async def CaptchaButton(chat_id, user_id, *, client, challenge=None, label=None):
    challenge = challenge or await captcha.get(client, chat_id, user_id)
    if not challenge:
        return None
    if label is None:
        _, label, _ = await GetCaptchaSettings(chat_id)
    if challenge["rules"]:
        return [
            [
                InlineKeyboardButton(
                    label,
                    url=f"https://t.me/{bot_username(client)}?start=captcha_button_{challenge['token']}",
                )
            ]
        ]
    return [[InlineKeyboardButton(label, callback_data=f"captcha_{challenge['token']}")]]


@callbackquery(
    filters=filters.regex("^captcha_[A-Za-z0-9_-]{16}$"), access=CallbackAccess(public=True)
)
async def CaptchaCallback(client: Client, callback_query: CallbackQuery):
    challenge = await captcha.from_callback(
        client, callback_query, callback_query.data[8:], {"button"}
    )
    if not challenge:
        return
    try:
        if challenge["rules"]:
            await callback_query.answer()
            return await ruleCaptchaButton(
                client,
                callback_query,
                challenge["chat_id"],
                challenge["welcome_id"],
                challenge=challenge,
            )
        if await captcha.complete(client, challenge):
            await callback_query.answer(tr("button_captcha.thank_for_your_time"))
        else:
            await callback_query.answer(tr("captcha.processing"))
    except (ValueError, RPCError):
        await callback_query.answer(tr("captcha.review_required"), show_alert=True)


async def buttonCaptchaRedirect(client, message):
    payload = captcha.start_payload(message)
    if not payload or payload[0] != "button":
        return
    challenge = await captcha.from_link(client, message, payload)
    if not challenge:
        return
    if challenge["stage"] not in {"button", "rules"} or not challenge["rules"]:
        return await message.reply(tr("captcha.expired_prompt"))
    await ruleCaptchaButton(
        client, message, challenge["chat_id"], challenge["welcome_id"], challenge=challenge
    )
