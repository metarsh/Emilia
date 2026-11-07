import html

from Emilia.custom_filter import command
from Emilia.database.rules import get_private_note, set_private_rule
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker

PRIVATE_RULES_TRUE = ["yes", "on"]
PRIVATE_RULES_FALSE = ["no", "off"]


@command("privaterules", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def private_rules(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await user_has_permission(message, privileges="can_change_info"):
        return

    command = message.text.split(" ")
    if not (len(command) == 1):
        args = command[1]

        if args in PRIVATE_RULES_TRUE:
            await message.reply(tr("private_rules.use_of_rules_will_send_the_rules"))
            await set_private_rule(chat_id, True)

        elif args in PRIVATE_RULES_FALSE:
            await message.reply(
                tr(
                    "private_rules.all_rules_commands_will_send_the_rules",
                    chat_title=html.escape(chat_title),
                ),
            )
            await set_private_rule(chat_id, False)

        else:
            await message.reply(tr("private_rules.i_only_understand_the_following_yes_no"))
    else:
        if await get_private_note(chat_id):
            await message.reply(tr("private_rules.use_of_rules_will_send_the_rules"))
        else:
            await message.reply(
                tr(
                    "private_rules.all_rules_commands_will_send_the_rules",
                    chat_title=html.escape(chat_title),
                )
            )
