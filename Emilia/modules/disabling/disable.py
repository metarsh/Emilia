from Emilia.custom_filter import command
from Emilia.utils.chat_status import check_user
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.disable import set_command_state


@command("disable", chat_scope="group_or_channel", allow_connected=True)
@anonadmin_checker
async def disable(client, message):
    if not await check_user(message, privileges="can_change_info"):
        return
    await set_command_state(message, disabled=True)
