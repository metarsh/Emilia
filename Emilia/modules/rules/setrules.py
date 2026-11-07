import html

from Emilia.custom_filter import command
from Emilia.database.rules import set_rules_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.saved_message import parse_saved_message


@command("setrules", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def set_rules(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await user_has_permission(message, privileges="can_change_info"):
        return

    _, get_rules, kind = parse_saved_message(message, named=False)
    if kind != 1:
        return await reply_usage(message, set_rules)

    await set_rules_db(chat_id, get_rules)
    await message.reply(
        tr("setrules.new_rules_set_successfully", chat_title=html.escape(chat_title))
    )
    return "NEW_RULES", None, None
