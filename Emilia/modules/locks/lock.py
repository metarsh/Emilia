from pyrogram.errors import BadRequest
from pyrogram.types import ChatPermissions

from Emilia.custom_filter import command
from Emilia.database.locks import lock_db
from Emilia.locales import tr
from Emilia.modules.locks import lock_map
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_bot, check_user
from Emilia.utils.decorators import anonadmin_checker


@command("lock", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def lock(client, message):
    chat_id = effective_chat_id(message)

    if not await check_bot(message, privileges=["can_delete_messages", "can_restrict_members"]):
        return

    if not await check_user(message, privileges="can_change_info"):
        return

    if not (len(message.text.split()) >= 2):
        return await message.reply(tr("lock.you_haven_t_specified_a_type_to"))

    LOCKS_LIST = lock_map.LocksMap.list()

    lock_args = message.text.split()[1:]

    LOCK_ITMES = []
    INCORRECT_ITEMS = []

    for lock in lock_args:
        if lock not in LOCKS_LIST:
            INCORRECT_ITEMS.append(lock)
        else:
            LOCK_ITMES.append(lock)

    if len(INCORRECT_ITEMS) != 0:
        text = tr("lock.unknown_lock_types")
        for item in INCORRECT_ITEMS:
            text += f"• {item}\n"
        text += tr("lock.check_locktypes")
        return await message.reply(text)

    for item in LOCK_ITMES:
        lock_value = lock_map.LocksMap[item].value
        await lock_db(chat_id, lock_value)

    text = "Locked:\n"
    for lock_arg in LOCK_ITMES:
        if len(LOCK_ITMES) != 1:
            text += f"• `{lock_arg}`\n"
        else:
            text = f"Locked `{lock_arg}`."

    if "all" in LOCK_ITMES:
        try:
            await client.set_chat_permissions(chat_id, ChatPermissions())
        except BadRequest:
            return await message.reply(tr("lock.non_admins_already_can_t_send_messages"))

    await message.reply(text)
