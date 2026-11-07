import html

from Emilia.custom_filter import command
from Emilia.database.locks import lockwarns_db, set_lockwarn_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker

LOCKWARN_TRUE = ["on", "yes"]
LOCKWARN_FALSE = ["off", "no"]


@command("lockwarns", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def lockwarns(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await user_has_permission(message, chat_id=chat_id, privileges="can_change_info"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]
        if args in LOCKWARN_TRUE:
            await message.reply(tr("lockwarns.lock_warns_have_been_enabled_any_user"))
            await set_lockwarn_db(chat_id, True)

        elif args in LOCKWARN_FALSE:
            await message.reply(tr("lockwarns.lock_warns_have_been_disabled_any_user"))
            await set_lockwarn_db(chat_id, False)

        else:
            await message.reply(tr("errors.invalid_toggle"))

    else:
        if await lockwarns_db(chat_id):
            await message.reply(
                tr(
                    "lockwarns.i_am_currently_warning_all_users_who",
                    chat_title=html.escape(chat_title),
                )
            )
        else:
            await message.reply(
                tr("lockwarns.i_am_not_warning_all_users_who", chat_title=html.escape(chat_title))
            )
