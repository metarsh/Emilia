from Emilia.custom_filter import command
from Emilia.database.welcome import GetCleanService, SetCleanService
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_admins
from Emilia.utils.decorators import anonadmin_checker

CLEAN_SERVICE_TRUE = ["on", "yes"]
CLEAN_SERVICE_FALSE = ["off", "no"]


@command("cleanservice", allow_connected=True, chat_scope="group")
@anonadmin_checker
async def CleanService(client, message):
    chat_id = effective_chat_id(message)

    if not (await check_admins(message, privileges="can_delete_messages")):
        return

    command = message.text.split(" ")
    if not (len(command) == 1):
        get_clean_service = command[1]

        if get_clean_service in CLEAN_SERVICE_TRUE:
            clean_service = True
            await SetCleanService(chat_id, clean_service)
            await message.reply(tr("clean_service.i_ll_be_deleting_all_service_messages"))

        elif get_clean_service in CLEAN_SERVICE_FALSE:
            clean_service = False
            await SetCleanService(chat_id, clean_service)
            await message.reply(tr("clean_service.i_ll_leave_service_messages"))

        else:
            await message.reply(tr("errors.invalid_toggle"))

    elif len(command) == 1:
        if await GetCleanService(chat_id):
            CleanServiceis = tr(
                "clean_service.am_currently_deleting_service_messages_when_new_members"
            )

        else:
            CleanServiceis = tr(
                "clean_service.am_not_currently_deleting_service_messages_when_members"
            )

        await message.reply(
            (
                tr(
                    "captcha.change_setting_try_command_again_followed_one_yes",
                    cleanserviceis=CleanServiceis,
                )
            ),
        )
