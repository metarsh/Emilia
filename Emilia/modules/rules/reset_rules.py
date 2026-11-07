import html

from Emilia.custom_filter import command
from Emilia.database.rules import set_rules_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker


@command(["resetrules", "clearrules"], chat_scope="group", allow_connected=True)
@anonadmin_checker
async def reset_rules(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await user_has_permission(message, privileges="can_change_info"):
        return

    await set_rules_db(chat_id, None)
    await message.reply(
        tr("reset_rules.rules_were_successfully_cleared", chat_title=html.escape(chat_title))
    )
