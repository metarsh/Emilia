from pyrogram.types import InlineKeyboardMarkup

from Emilia.custom_filter import command
from Emilia.database.welcome import (
    DEFAUT_WELCOME,
    GetCaptchaSettings,
    GetCleanService,
    GetWelcome,
    GetWelcomemessageOnOff,
    SetWelcomeMessageOnOff,
    isGetCaptcha,
    isWelcome,
)
from Emilia.locales import tr
from Emilia.utils.button_gen import button_markdown_parser
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_user
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.message_actor import actor_user
from Emilia.utils.welcome_format import DefaultWelcomeFillings
from Emilia.utils.welcome_sender import SendWelcomeMessage

WELCOME_TRUE = ["on", "yes"]
WELCOME_FALSE = ["off", "no"]


@command("welcome", allow_connected=True, chat_scope="group")
@anonadmin_checker
async def Welcome(client, message):
    chat_id = effective_chat_id(message)

    if not await check_user(message, privileges="can_change_info"):
        return

    if len(message.text.split()) >= 2:
        GetWelcomeArg = message.text.split()[1]
        if GetWelcomeArg in WELCOME_TRUE:
            await SetWelcomeMessageOnOff(chat_id, welcome_message=True)
            await message.reply(tr("welcome.i_ll_be_welcoming_all_new_members"))

        elif GetWelcomeArg in WELCOME_FALSE:
            await SetWelcomeMessageOnOff(chat_id, welcome_message=False)
            await message.reply(tr("welcome.i_ll_stay_quiet_when_new_members"))

        elif GetWelcomeArg == "noformat":
            await welcomeformat(message, chat_id, noformat=True)

        else:
            await message.reply(tr("errors.invalid_toggle"))

    elif len(message.text.split()) == 1:
        await welcomeformat(message, chat_id, noformat=False)


async def welcomeformat(message, chat_id, noformat=True):
    if await GetWelcomemessageOnOff(chat_id):
        WelcomeMessage = "true"
    else:
        WelcomeMessage = "false"

    if await GetCleanService(chat_id):
        CleanService = "true"
    else:
        CleanService = "false"

    if await isGetCaptcha(chat_id):
        captcha_mode, captcha_text, captcha_kick_time = await GetCaptchaSettings(chat_id)

        if captcha_mode is None:
            captcha_mode = "button"

        if captcha_text is None:
            captcha_text = tr("welcome.click_here_prove_re_human")

        if captcha_kick_time is None:
            captcha_kick_time = "disabled"

        captcha = tr(
            "welcome.current_captcha_mode_captcha_button_will_say_captcha",
            captcha_mode=captcha_mode,
            captcha_text=captcha_text,
            captcha_kick_time=captcha_kick_time,
        )
    else:
        captcha = tr("welcome.captchas_disabled")

    WELCOME_MESSAGE = tr(
        "welcome.am_currently_welcoming_users_am_currently_deleting_services",
        welcomemessage=WelcomeMessage,
        cleanservice=CleanService,
        captcha=captcha,
    )

    WelcomeSentMessage = await message.reply(WELCOME_MESSAGE)

    if await isWelcome(chat_id):
        Content, Text, DataType = await GetWelcome(chat_id)
        Text, buttons = button_markdown_parser(Text)

        reply_markup = None
        if len(buttons) > 0:
            reply_markup = InlineKeyboardMarkup(buttons)
        if noformat:
            WelcomeSentMessage = await SendWelcomeMessage(
                message._client,
                message,
                None,
                Content,
                Text,
                DataType,
                reply_markup=reply_markup,
            )
        else:
            WelcomeSentMessage = await SendWelcomeMessage(
                message._client,
                message,
                actor_user(message),
                Content,
                Text,
                DataType,
                reply_markup=reply_markup,
            )
    else:
        if noformat:
            await WelcomeSentMessage.reply(DEFAUT_WELCOME)
        else:
            welcome_message = await DefaultWelcomeFillings(
                message, DEFAUT_WELCOME, actor_user(message)
            )
            await WelcomeSentMessage.reply(welcome_message)
