from Emilia.custom_filter import command
from Emilia.database.welcome import GetCaptchaSettings, SetCaptchaText
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_bot_admin, user_has_permission
from Emilia.utils.decorators import anonadmin_checker


@command(["setcaptchatext", "resetcaptchatext"], chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
async def SetCaptchatext(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(
        message, chat_id=chat_id, privileges="can_change_info", fresh=True
    ):
        return

    if not await is_bot_admin(message, chat_id=chat_id, silent=True, fresh=True):
        await message.reply(
            tr("captcha.i_need_to_be_admin_with_the"),
        )
        return

    if message.command[0].lower() == "resetcaptchatext":
        await SetCaptchaText(chat_id, None)
        return await message.reply(tr("setcaptchatext.reset_the_captcha_button_text"))
    CaptchaText = " ".join(message.text.split()[1:])
    if CaptchaText:
        await SetCaptchaText(chat_id, CaptchaText)
        await message.reply(tr("setcaptchatext.updated_the_captcha_button_text"))

    else:
        captcha_mode, captcha_text, captcha_kick_time = await GetCaptchaSettings(chat_id)

        await message.reply(
            (tr("setcaptchatext.users_will_be_welcomed_with_a_button", captcha_text=captcha_text)),
        )
