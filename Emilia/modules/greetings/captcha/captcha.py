from Emilia.custom_filter import command
from Emilia.database.welcome import SetCaptcha, isGetCaptcha
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import bot_has_permission, user_has_permission
from Emilia.utils.decorators import anonadmin_checker

CAPTCHA_WELCOME_TRUE = ["on", "yes"]
CAPTCHA_WELCOME_FALSE = ["off", "no"]


@command("captcha", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
async def Captcha(client, message):
    chat_id = effective_chat_id(message)

    if not await bot_has_permission(
        message, chat_id=chat_id, privileges="can_restrict_members", fresh=True, silent=False
    ):
        return

    if not await user_has_permission(
        message, chat_id=chat_id, privileges="can_restrict_members", fresh=True, silent=False
    ):
        return

    if len(message.text.split()) >= 2:
        get_args = message.text.split()[1].lower()

        if get_args in CAPTCHA_WELCOME_TRUE:
            await SetCaptcha(chat_id, True)
            await message.reply(
                tr("captcha.captchas_have_been_enabled_i_will_now"),
            )

        elif get_args in CAPTCHA_WELCOME_FALSE:
            await SetCaptcha(chat_id, False)
            await message.reply(tr("captcha.captchas_have_been_disabled_users_can_join"))
        else:
            await message.reply(tr("captcha.invalid_option"))

    elif len(message.text.split()) == 1:
        if await isGetCaptcha(chat_id):
            CaptchaSetting = tr("captcha.users_will_asked_complete_captcha_before_being_allowed")
        else:
            CaptchaSetting = tr("captcha.users_will_not_muted_when_joining_chat")

        await message.reply(
            (
                tr(
                    "captcha.change_setting_try_command_again_followed_one_yes",
                    cleanserviceis=CaptchaSetting,
                )
            ),
        )
