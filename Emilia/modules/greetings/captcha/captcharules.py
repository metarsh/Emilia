from Emilia.custom_filter import command
from Emilia.database.welcome import isRuleCaptcha, setRuleCaptcha
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker

CAPTCHARULE_TRUE = ["on", "yes"]
CAPTCHARULE_FALSE = ["off", "no"]


@command("captcharules", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
async def rulecaptcha(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(
        message, chat_id=chat_id, privileges="can_change_info", fresh=True
    ):
        return

    if len(message.text.split()) >= 2:
        command_arg = message.text.split()[1].lower()
        if command_arg in CAPTCHARULE_TRUE:
            await setRuleCaptcha(chat_id=chat_id, rule_captcha=True)
            await message.reply(tr("captcharules.captcha_rules_have_been_enable_users_now"))

        elif command_arg in CAPTCHARULE_FALSE:
            await setRuleCaptcha(chat_id=chat_id, rule_captcha=False)
            await message.reply(tr("captcharules.captcha_rules_have_been_disabled_users_will"))

        else:
            await message.reply(
                tr("captcharules.that_isn_t_a_boolean_excpected_one", command_arg=command_arg)
            )

    else:
        if await isRuleCaptcha(chat_id=chat_id):
            text = tr("captcharules.captcha_rules_currently_enabled_users_will_asked_accept")
        else:
            text = tr("captcharules.captcha_rules_currently_disabled")

        await message.reply(
            tr("captcharules.change_setting_try_command_agin_followed_yes_no", current_setting=text)
        )
