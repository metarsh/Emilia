from Emilia.custom_filter import DISABLE_COMMANDS, command
from Emilia.locales import tr
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker


@command("disableable", chat_scope="group_or_channel", allow_connected=True)
@anonadmin_checker
async def disable_list(client, message):
    if not await is_user_admin(message):
        return

    text_header = tr("disableable.following_commands_can_disabled")
    for diable in DISABLE_COMMANDS:
        text_header += f"- `{diable}`\n"

    await message.reply(text_header)
