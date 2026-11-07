import html
from functools import wraps

from pyrogram.enums import ParseMode

from Emilia.database.disable import get_disabled, get_disabledel, set_commands_state
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import bot_has_permission, is_user_admin
from Emilia.utils.command_help import reply_usage


async def set_command_state(message, *, disabled: bool):
    from Emilia.custom_filter import DISABLE_COMMANDS

    names = list(dict.fromkeys(name.lower() for name in message.command[1:]))
    if not names:
        return await reply_usage(message)
    unknown = [name for name in names if name not in DISABLE_COMMANDS]
    if unknown:
        text = tr(
            "disable.unknown_command_disable" if disabled else "enable.unknown_command_enable"
        )
        text += "\n".join(f"- <code>{html.escape(name)}</code>" for name in unknown)
        text += tr("disable.check_disableable")
        return await message.reply(text, parse_mode=ParseMode.HTML)
    chat_id = effective_chat_id(message)
    await set_commands_state(chat_id, names, disabled=disabled)
    state = "Disabled" if disabled else "Enabled"
    text = f"{state}:\n" + "\n".join(f"- <code>{html.escape(name)}</code>" for name in names)
    await message.reply(text, parse_mode=ParseMode.HTML)


def disable(func):
    @wraps(func)
    async def wrapper(client, message):
        text = message.text or message.caption or ""
        if not text.split():
            return
        if await is_user_admin(message, silent=True):
            return await func(client, message)
        if not message.command:
            return
        command = message.command[0].lower()
        chat_id = effective_chat_id(message)
        if command in await get_disabled(chat_id):
            if (
                chat_id == message.chat.id
                and await get_disabledel(chat_id)
                and await bot_has_permission(message, privileges="can_delete_messages", silent=True)
            ):
                await message.delete()
            return
        return await func(client, message)

    return wrapper
