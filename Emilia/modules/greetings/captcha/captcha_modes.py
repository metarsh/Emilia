from Emilia.custom_filter import command
from Emilia.database.welcome import GetCaptchaSettings, SetCaptchaMode
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_bot_admin, user_has_permission
from Emilia.utils.decorators import anonadmin_checker

CAPTCHA_MODE_MAP = {
    "text": tr("captcha_modes.text_captchas_require_user_answer_captcha_containing_letters"),
    "math": tr("captcha_modes.math_captchas_require_user_solve_basic_maths_question"),
    "button": tr("captcha_modes.button_captchas_simply_require_user_press_button_their"),
}


@command("captchamode", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
async def CaptchaMode(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(
        message, chat_id=chat_id, privileges="can_change_info", fresh=True
    ):
        return

    if not await is_bot_admin(message, chat_id=chat_id, silent=True, fresh=True):
        await message.reply(tr("captcha.i_need_to_be_admin_with_the"))
        return

    command = message.text.split()
    if not (len(command) == 1):
        GetArgs = command[1].lower()
        if GetArgs in {"text", "image"}:
            await SetCaptchaMode(chat_id, "text")
            await message.reply(
                tr("captcha_modes.captcha_set_text", instructions=CAPTCHA_MODE_MAP["text"])
            )

        elif GetArgs == "math":
            await SetCaptchaMode(chat_id, "math")
            await message.reply(tr("captcha_modes.captcha_set_math", math=CAPTCHA_MODE_MAP["math"]))

        elif GetArgs == "button":
            await SetCaptchaMode(chat_id, "button")
            await message.reply(
                tr("captcha_modes.captcha_set_button", button=CAPTCHA_MODE_MAP["button"])
            )

        else:
            await message.reply(
                tr("captcha_modes.not_recognised_captcha_mode_try_one_button_math", getargs=GetArgs)
            )
    else:
        captcha_mode, captcha_text, captcha_kick_time = await GetCaptchaSettings(chat_id)

        await message.reply(
            tr(
                "captcha_modes.current_captcha_mode_available_captcha_modes_button_math",
                captcha_mode=captcha_mode,
                captcha_mode_map=CAPTCHA_MODE_MAP[captcha_mode],
            )
        )
