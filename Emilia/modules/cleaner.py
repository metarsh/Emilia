from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType
from pyrogram.errors import RPCError

from Emilia.custom_filter import command
from Emilia.database.cleaner import get_cleancommand_cached, set_cleancommand
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_user
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel


@command(
    ["cleancommand", "cleancommands", "cleancmd", "cleanblue", "nocleancommand", "keepcommand"],
    allow_connected=True,
    chat_scope="group",
)
@anonadmin_checker
@log_to_channel
async def _cleancommand(_, message):
    chat_id = effective_chat_id(message)
    if not await check_user(message, privileges="can_delete_messages"):
        return
    cmd = message.command[0]
    args = [x.lower() for x in message.text.split()[1:]]
    check = await get_cleancommand_cached(chat_id)

    if cmd in ("nocleancommand", "keepcommand"):
        if not check:
            await message.reply_text(tr("cleaner.command_cleaning_has_been_already_disabled_in"))
            return
        await set_cleancommand(chat_id, False)
        await message.reply_text(tr("cleaner.disabled_command_cleaning_successfully"))
        return "DISABLED_COMMAND_CLEANING", None, None

    if not args:
        status_text = "enabled" if check else "disabled"
        await message.reply_text(
            tr("cleaner.command_cleaning_currently_chat", status_text=status_text)
        )
        return

    first_arg = args[0]
    if first_arg in ("on", "yes", "true", "enable"):
        if not check:
            await set_cleancommand(chat_id, True)
            await message.reply_text(tr("cleaner.command_cleaning_enabled"))
            return "ENABLED_COMMAND_CLEANING", None, None
        return await message.reply_text(tr("cleaner.command_cleaning_has_been_already_enabled_in"))
    elif first_arg in ("off", "no", "false", "disable"):
        if not check:
            return await message.reply_text(
                tr("cleaner.command_cleaning_has_been_already_disabled_in")
            )
        await set_cleancommand(chat_id, False)
        await message.reply_text(tr("cleaner.disabled_command_cleaning_successfully"))
        return "DISABLED_COMMAND_CLEANING", None, None
    else:
        await reply_usage(message, _cleancommand)
        return


@Client.on_message(filters.group | filters.private, group=16)
async def _delmessage(_, message):
    if not message.chat:
        return
    chat_id = message.chat.id
    if not await get_cleancommand_cached(chat_id):
        return
    entities = message.entities or message.caption_entities
    if not entities:
        return
    try:
        first_entity = entities[0]
        if first_entity.offset == 0 and first_entity.type == MessageEntityType.BOT_COMMAND:
            await message.delete()
    except RPCError:
        pass
