from Emilia.custom_filter import command
from Emilia.database.report import get_report, reports_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker

REPORTS_TRUE = ["yes", "on"]
REPORTS_FALSE = ["no", "off"]


@command("reports", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def reports(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, chat_id=chat_id, privileges="can_change_info"):
        return

    if len(message.text.split()) >= 2:
        report_args = message.text.split()[1]

        if report_args in REPORTS_TRUE:
            await message.reply(tr("reports.users_will_now_be_able_to_report"))
            await reports_db(chat_id, True)

        elif report_args in REPORTS_FALSE:
            await message.reply(tr("reports.users_will_no_longer_be_able_to"))
            await reports_db(chat_id, False)

        else:
            await message.reply(tr("errors.invalid_toggle"))
    else:
        if await get_report(chat_id):
            text = tr("reports.reports_currently_enabled_chat_users_can_use_report")
        else:
            text = tr("reports.reports_currently_disabled_chat")

        await message.reply(
            tr("reports.change_setting_try_command_again_one_following_args", current_setting=text)
        )
