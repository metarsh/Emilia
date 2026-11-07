from Emilia.custom_filter import command
from Emilia.database.welcome import GetCleanWelcome, SetCleanWelcome
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_admins
from Emilia.utils.decorators import anonadmin_checker

CLEAN_WELCOME_TRUE = ["on", "yes"]
CLEAN_WELCOME_FALSE = ["off", "no"]


@command("cleanwelcome", allow_connected=True, chat_scope="group")
@anonadmin_checker
async def CleanWelcome(client, message):
    chat_id = effective_chat_id(message)

    if not await check_admins(message, privileges=None):
        return

    command = message.text.split(" ")
    if not (len(command) == 1):
        get_args = command[1]
        if get_args in CLEAN_WELCOME_TRUE:
            clean_welcome = True
            await SetCleanWelcome(chat_id, clean_welcome)
            await message.reply(
                tr("clean_welcome.i_ll_be_deleting_all_old_welcome"),
            )

        elif get_args in CLEAN_WELCOME_FALSE:
            clean_welcome = False
            await SetCleanWelcome(chat_id, clean_welcome)
            await message.reply(tr("clean_welcome.i_ll_leave_old_welcome_goodbye_messages"))

    elif len(command) == 1:
        if await GetCleanWelcome(chat_id):
            CleanMessage = tr("clean_welcome.am_currently_deleting_old_welcome_messages_when_new")
        else:
            CleanMessage = tr("clean_welcome.am_not_currently_deleting_old_welcome_messages_when")

        await message.reply(
            (
                tr(
                    "captcha.change_setting_try_command_again_followed_one_yes",
                    cleanserviceis=CleanMessage,
                )
            ),
        )
