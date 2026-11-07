from Emilia.custom_filter import command
from Emilia.database.rules import get_rules_button, set_rule_button
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker


@command("setrulesbutton", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def set_rules(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, privileges="can_change_info"):
        return

    command = message.text.split(" ")
    if len(command) == 1:
        current_rules_button = await get_rules_button(chat_id)
        return await message.reply(
            tr(
                "set_rules_button.rules_button_will_called_change_button_name_try",
                current_rules_button=current_rules_button,
            ),
        )

    rules_button = " ".join(command[1:])

    await set_rule_button(chat_id, rules_button)
    await message.reply(tr("set_rules_button.updated_the_rules_button_name"))
