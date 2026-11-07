import html

from Emilia.custom_filter import command
from Emilia.database.warnings import set_warn_limit_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker


@command(["warnlimit", "setwarnlimit"], chat_scope="group", allow_connected=True)
@anonadmin_checker
async def setWarnLimit(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await user_has_permission(message, privileges="can_change_info"):
        return

    if not len(message.text.split()) >= 2:
        await reply_usage(message, setWarnLimit)
        return

    warn_limit_arg = message.text.split()[1]
    if not warn_limit_arg.isdigit():
        return await message.reply(
            tr("set_warn_limit.not_valid_integer", warn_limit_arg=warn_limit_arg)
        )

    if int(warn_limit_arg) > 50:
        return await message.reply(tr("set_warn_limit.the_maximum_warning_limit_is_50"))

    if int(warn_limit_arg) == 0:
        return await message.reply(tr("set_warn_limit.the_warning_limit_has_to_be_set"))

    await message.reply(
        tr(
            "set_warn_limit.warn_limit_settings_has_updated",
            chat_title=html.escape(chat_title),
            warn_limit_arg=warn_limit_arg,
        ),
    )
    await set_warn_limit_db(chat_id, int(warn_limit_arg))
