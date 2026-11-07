import io

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.custom_filter import callbackquery
from Emilia.database.rules import get_rules
from Emilia.locales import tr
from Emilia.services import captcha
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.tasks import finish_cleanup


async def ruleCaptchaButton(client, message, chat_id, message_id, *, challenge=None):
    challenge = challenge or await captcha.get(client, chat_id, message.from_user.id)
    if not challenge or (not challenge.get("claimed") and not await captcha.claim(challenge)):
        return
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("captcharules_button.i_have_read_and_accept_the_rules"),
                    callback_data=f"captcharule_{challenge['token']}",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        ]
    )
    try:
        rules = await get_rules(chat_id) or tr("captcha.rules_unset")
        caption = tr("captcha.rules_prompt")
        if challenge.get("chat_title"):
            key = (
                "autoapprove.welcome_please_read_agree_following_rules_before_joining"
                if (challenge["source"] == "join_request")
                else "captcha.rules_for_chat"
            )
            rules = tr(key, chat_title=challenge["chat_title"], rules_text=rules)
            if challenge["source"] == "join_request":
                caption = tr(
                    "autoapprove.welcome_please_read_attached_rules_click_agree_join",
                    chat_title=challenge["chat_title"],
                )
        private_chat_id = challenge.get("private_chat_id", message.from_user.id)
        if len(rules.encode("utf-16-le")) // 2 > 4096:
            with io.BytesIO(rules.encode()) as document:
                document.name = "rules.txt"
                sent = await client.send_document(
                    private_chat_id,
                    document,
                    caption=caption,
                    reply_markup=keyboard,
                )
        else:
            sent = await client.send_message(private_chat_id, rules, reply_markup=keyboard)
        if await captcha.bind_prompt(challenge, sent, stage="rules"):
            return sent
        await sent.delete()
    except BaseException:
        if challenge.get("claimed"):
            await finish_cleanup(captcha.release(challenge))
        raise


@callbackquery(
    filters=filters.regex("^captcharule_[A-Za-z0-9_-]{16}$"), access=CallbackAccess(public=True)
)
async def captchaRules(client: Client, callback_query: CallbackQuery):
    challenge = await captcha.from_callback(
        client, callback_query, callback_query.data[12:], {"rules"}
    )
    if not challenge:
        return
    try:
        if not await captcha.complete(client, challenge):
            return await callback_query.answer(tr("captcha.processing"))
    except (ValueError, RPCError):
        return await callback_query.answer(tr("captcha.review_required"), show_alert=True)
    await callback_query.answer(tr("captcharules_button.you_have_passed_the_captcha"))
    text = (
        tr("autoapprove.thank_you_for_agreeing_to_the_rules")
        if (challenge["source"] == "join_request")
        else tr("captcharules_button.you_have_passed_the_captcha")
    )
    try:
        if callback_query.message.document:
            await callback_query.edit_message_caption(text, reply_markup=None)
        else:
            await callback_query.edit_message_text(text, reply_markup=None)
    except RPCError:
        pass
