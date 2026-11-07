from Emilia.custom_filter import command
from Emilia.database.locks import get_locks
from Emilia.locales import tr
from Emilia.modules.locks import lock_map
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker


@command("locks", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def locks(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    LOCKS_LIST = await get_locks(chat_id)

    if len(LOCKS_LIST) == 0:
        return await message.reply(tr("locks.no_items_locked_in_this_chat"))

    if 1 in LOCKS_LIST:
        return await message.reply(tr("locks.jokes_on_you_everything_s_locked"))

    text = tr("locks.these_currently_locked_items")
    for item in LOCKS_LIST:
        lock_name = lock_map.LocksMap(item).name
        text += f"• `{lock_name}`\n"

    await message.reply(text)
