from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.database.notes import is_pnote_on, set_private_note
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker

PRIVATE_NOTES_TRUE = ["on", "true", "yes", "y"]
PRIVATE_NOTES_FALSE = ["off", "false", "no", "n"]


@command("privatenotes", allow_connected=True)
@anonadmin_checker
async def PrivateNote(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message, chat_id=chat_id):
        return

    command = message.text.split(" ")
    if not (len(command) == 1):
        if command[1] in PRIVATE_NOTES_TRUE:
            await message.reply(
                tr(
                    "set_private_notes.will_now_send_message_chat_button_redirecting_pm",
                    bot_name=Config.BOT_NAME,
                ),
            )
            await set_private_note(chat_id, True)

        elif command[1] in PRIVATE_NOTES_FALSE:
            await message.reply(
                tr("set_private_notes.will_now_send_notes_straight_group", bot_name=Config.BOT_NAME)
            )
            await set_private_note(chat_id, False)

        else:
            await message.reply(
                tr(
                    "set_private_notes.failed_to_get_boolean_value_from_input",
                    input=message.text.split()[1],
                ),
            )
    else:
        if await is_pnote_on(chat_id):
            await message.reply(
                tr("notes.private_delivery_enabled", bot_name=Config.BOT_NAME),
            )
        else:
            await message.reply(tr("set_private_notes.your_notes_are_currently_being_sent_in"))
