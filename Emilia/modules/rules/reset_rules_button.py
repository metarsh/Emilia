from Emilia.custom_filter import command
from Emilia.database.rules import set_rule_button
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker


@command("resetrulesbutton", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def reset_rules(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, privileges="can_change_info"):
        return

    await set_rule_button(chat_id, "Rules")
    await message.reply(tr("reset_rules_button.reset_the_rules_button_name_to_default"))
