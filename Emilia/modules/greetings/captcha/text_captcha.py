import random
import re
from pathlib import Path

from captcha.image import ImageCaptcha
from pyrogram import Client, filters
from pyrogram.errors import RPCError
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.config import Config
from Emilia.custom_filter import callbackquery
from Emilia.database.welcome import GetCaptchaSettings
from Emilia.locales import tr
from Emilia.modules.greetings.captcha.captcharules_button import ruleCaptchaButton
from Emilia.modules.greetings.utils.actions import failedAction
from Emilia.modules.greetings.utils.random_string_gen import RandomStringGen, mathCaptchaGen
from Emilia.services import captcha
from Emilia.utils.client_context import bot_username
from Emilia.utils.executors import run_in_thread
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.tasks import finish_cleanup


def _keyboard(challenge):
    buttons = [
        InlineKeyboardButton(str(value), callback_data=f"textc_{challenge['token']}:{index}")
        for index, value in enumerate(challenge["choices"])
    ]
    return InlineKeyboardMarkup([buttons[index : index + 3] for index in range(0, len(buttons), 3)])


def _caption(challenge, progress, intro=None):
    if intro is None and challenge.get("chat_title"):
        intro = tr("captcha.for_chat", chat_title=challenge["chat_title"])
    return "\n\n".join(part for part in (intro, progress, tr("captcha.answer_prompt")) if part)


async def textCaptcha(chat_id, user_id, *, client, challenge=None, label=None):
    challenge = challenge or await captcha.get(client, chat_id, user_id)
    if not challenge:
        return None
    if label is None:
        _, label, _ = await GetCaptchaSettings(chat_id)
    return [
        [
            InlineKeyboardButton(
                label,
                url=f"https://t.me/{bot_username(client)}?start=captcha_{challenge['stage']}_{challenge['token']}",
            )
        ]
    ]


async def textCaptchaRedirect(client, message):
    payload = captcha.start_payload(message)
    if not payload or payload[0] not in {"text", "math"}:
        return
    mode = payload[0]
    challenge = await captcha.from_link(client, message, payload)
    if not challenge:
        return
    if challenge["stage"] == "rules" and challenge["rules"]:
        return await ruleCaptchaButton(
            client, message, challenge["chat_id"], challenge["welcome_id"], challenge=challenge
        )
    if mode != challenge["stage"]:
        return await message.reply(tr("captcha.expired_prompt"))
    await dispatch_text_math_captcha(
        client, challenge["user_id"], challenge["chat_id"], mode, message, challenge=challenge
    )


@callbackquery(
    filters=filters.regex("^textc_[A-Za-z0-9_-]{16}:\\d{1,2}$"), access=CallbackAccess(public=True)
)
async def textCaptchaCallBack(client: Client, callback_query: CallbackQuery):
    token, index = callback_query.data[6:].split(":")
    challenge = await captcha.from_callback(client, callback_query, token, {"text", "math"})
    if not challenge:
        return
    index = int(index)
    if index >= len(challenge.get("choices", [])):
        return await callback_query.answer(
            tr("custom_filter.this_button_has_expired"), show_alert=True
        )
    await _answer_challenge(
        client,
        challenge,
        str(challenge["choices"][index]),
        callback_query,
        callback_query.message,
        callback=True,
    )


@Client.on_message(filters.private & filters.text & filters.reply, group=1)
async def textCaptchaReply(client, message):
    if (message.text or "").startswith(Config.TRIGGERS):
        return
    prompt = message.reply_to_message
    if not prompt or not prompt.reply_markup or not message.from_user:
        return
    for row in prompt.reply_markup.inline_keyboard:
        for button in row:
            match = re.fullmatch(r"textc_([A-Za-z0-9_-]{16}):\d{1,2}", button.callback_data or "")
            if match:
                challenge = await captcha.from_prompt(
                    client, message.from_user.id, match[1], prompt, {"text", "math"}
                )
                if challenge:
                    answer = message.text.strip().casefold()
                    if challenge["stage"] == "math" and len(answer) <= 16:
                        try:
                            answer = str(int(answer))
                        except ValueError:
                            pass
                    await _answer_challenge(client, challenge, answer, message, prompt)
                else:
                    await message.reply_text(tr("captcha.expired_prompt"))
                return


async def _edit_prompt(message, caption, reply_markup=None):
    try:
        await message.edit_caption(caption, reply_markup=reply_markup)
    except RPCError:
        pass


async def _answer_challenge(client, challenge, answer, actor, prompt, *, callback=False):
    async def notify(text):
        try:
            if callback:
                await actor.answer(text)
            else:
                await actor.reply_text(text)
        except RPCError:
            pass

    if not await captcha.claim(challenge):
        return await notify(tr("captcha.processing"))
    try:
        if answer == challenge["answer"]:
            if challenge["rules"]:
                await notify(tr("text_captcha.you_passed_the_captcha"))
                sent = await ruleCaptchaButton(
                    client,
                    actor,
                    challenge["chat_id"],
                    challenge["welcome_id"],
                    challenge=challenge,
                )
                if sent:
                    await _edit_prompt(prompt, tr("captcha.accept_rules_prompt"))
            elif await captcha.complete(client, challenge, claimed=True):
                key = (
                    "autoapprove.captcha_passed_you_have_been_approved_to"
                    if (challenge["source"] == "join_request")
                    else "text_captcha.you_passed_the_captcha"
                )
                await notify(tr(key))
                await _edit_prompt(prompt, tr(key))
            return
        attempts = challenge["attempts"] + 1
        if attempts >= captcha.MAX_ATTEMPTS:
            await notify(tr("text_captcha.you_failed_this_captcha"))
            await failedAction(
                client,
                actor,
                challenge["user_id"],
                challenge["chat_id"],
                challenge["welcome_id"],
                source=challenge["source"],
                challenge=challenge,
            )
            await captcha.remove(challenge)
            return await _edit_prompt(prompt, tr("text_captcha.you_failed_this_captcha"))
        await notify(tr("text_captcha.you_have_clicked_on_wrong_captcha_button"))
        try:
            await _edit_prompt(
                prompt,
                _caption(
                    challenge,
                    tr("captcha.attempts_remaining", count=captcha.MAX_ATTEMPTS - attempts),
                ),
                reply_markup=_keyboard(challenge),
            )
        finally:
            await finish_cleanup(captcha.release(challenge, attempts=attempts))
    except (ValueError, RPCError):
        if challenge.get("claimed"):
            await finish_cleanup(captcha.release(challenge))
        await notify(tr("captcha.review_required"))
    except BaseException:
        if challenge.get("claimed"):
            await finish_cleanup(captcha.release(challenge))
        raise


async def dispatch_text_math_captcha(
    client, user_id, chat_id, mode, message=None, caption=None, *, challenge=None
):
    challenge = challenge or await captcha.get(client, chat_id, user_id)
    if not challenge or challenge["stage"] != mode or not await captcha.claim(challenge):
        return
    try:
        if challenge.get("rendered"):
            choices, answer, rendered = (
                challenge["choices"],
                challenge["answer"],
                challenge["rendered"],
            )
        elif mode == "text":
            choices = RandomStringGen()
            rendered = answer = random.SystemRandom().choice(choices)
        elif mode == "math":
            numbers, choices = mathCaptchaGen()
            rendered = f"{numbers['num01']} + {numbers['num02']} = ?"
            answer = str(numbers["answer"])
        else:
            raise ValueError("Unknown CAPTCHA mode")

        def render():
            image = ImageCaptcha(
                width=320 if mode == "math" else 270,
                height=90,
                fonts=[str(Path(Config.FONT_DIRECTORY) / "DejaVuSans.ttf")],
                font_sizes=(50,),
            )
            stream = image.generate(rendered)
            stream.name = "captcha.png"
            return stream

        image = await run_in_thread(render)
        try:
            progress = tr("captcha.complete_prompt")
            if challenge["attempts"]:
                progress = tr(
                    "captcha.attempts_remaining", count=captcha.MAX_ATTEMPTS - challenge["attempts"]
                )
            sent = await client.send_photo(
                challenge.get("private_chat_id", user_id),
                image,
                caption=_caption(challenge, progress, caption),
                reply_markup=_keyboard({**challenge, "choices": choices}),
            )
            if await captcha.bind_prompt(
                challenge, sent, choices=choices, answer=answer, rendered=rendered
            ):
                return sent
            await sent.delete()
        finally:
            image.close()
    except BaseException:
        if challenge.get("claimed"):
            await finish_cleanup(captcha.release(challenge))
        raise
