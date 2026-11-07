from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_admins
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.get_user import get_user_id
from Emilia.utils.restrictions import restrict_member


@command("unmute", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def unmute(client, message):
    chat_id = effective_chat_id(message)

    if not await check_admins(message, privileges="can_restrict_members"):
        return

    user_info = await get_user_id(message)
    if user_info is None:
        return
    user_id = user_info.id

    await restrict_member(chat_id, user_id, can_send_messages=True, client=client)

    await message.reply(tr("unmute.alright_they_can_speak_again"))
    return "UNMUTE", user_id, user_info.first_name
