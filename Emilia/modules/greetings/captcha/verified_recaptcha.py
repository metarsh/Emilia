from Emilia.custom_filter import command
from Emilia.database.welcome import isReCaptcha, setReCaptcha
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker

RECAPTCHA_TRUE = ["on", "yes"]
RECAPTCHA_FALSE = ["off", "no"]


@command("recaptcha", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
async def reCaptcha(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message, chat_id=chat_id, fresh=True):
        return

    if len(message.text.split()) >= 2:
        command_arg = message.text.split()[1].lower()

        if command_arg in RECAPTCHA_TRUE:
            await setReCaptcha(chat_id=chat_id, reCaptcha=True)
            await message.reply(tr("verified_recaptcha.from_now_on_i_ll_ask_the"))

        elif command_arg in RECAPTCHA_FALSE:
            await setReCaptcha(chat_id=chat_id, reCaptcha=False)
            await message.reply(tr("verified_recaptcha.i_won_t_ask_the_captcha_to"))

        else:
            await message.reply(
                tr("verified_recaptcha.this_isn_t_a_boolean_excpected_one", command_arg=command_arg)
            )

    else:
        if await isReCaptcha(chat_id=chat_id):
            await message.reply(tr("verified_recaptcha.recaptcha_enabled_i_m_asking_the_captcha"))
        else:
            await message.reply(tr("verified_recaptcha.recaptcha_disabled_i_m_not_asking_the"))
