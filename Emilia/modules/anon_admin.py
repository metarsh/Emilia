import html

from Emilia.custom_filter import command
from Emilia.database.chats_settings import anonadmin_db, get_anon_setting
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import is_chat_owner
from Emilia.utils.decorators import anonadmin_checker

ANONADMIN_TRUE = ["yes", "on"]
ANONADMIN_FALSE = ["no", "off"]


@command("anonadmin", chat_scope="group", allow_connected=True)
@anonadmin_checker(owner_only=True)
async def anon_admin(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await is_chat_owner(message, chat_id=chat_id, silent=False):
        return

    if len(message.command) >= 2:
        args = message.command[1].lower()

        if args in ANONADMIN_TRUE:
            await anonadmin_db(chat_id, True)
            await message.reply(
                tr(
                    "anonymous_admin.anon_admin_setting_has_updated_true",
                    chat_title=html.escape(chat_title),
                )
            )
        elif args in ANONADMIN_FALSE:
            await anonadmin_db(chat_id, False)
            await message.reply(
                tr(
                    "anonymous_admin.anon_admin_setting_has_updated_false",
                    chat_title=html.escape(chat_title),
                )
            )
        else:
            await message.reply(
                tr("anonymous_admin.failed_to_get_boolean_from_input_expected", arguments=args)
            )

    else:
        if await get_anon_setting(chat_id):
            await message.reply(
                tr(
                    "anonymous_admin.currently_allows_all_anonymous_admins_use_any_admin",
                    chat_title=html.escape(chat_title),
                )
            )
        else:
            await message.reply(
                tr(
                    "anonymous_admin.currently_requires_anonymous_admins_press_button_confirm_their",
                    chat_title=html.escape(chat_title),
                )
            )
