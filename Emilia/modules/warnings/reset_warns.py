from Emilia.custom_filter import command
from Emilia.database.warnings import count_user_warn, reset_user_warns
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.get_user import get_user_id


@command(["rmwarns", "resetwarn", "resetwarns"], chat_scope="group", allow_connected=True)
@anonadmin_checker
async def reset_warn(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    user_info = await get_user_id(message)
    if user_info is None:
        return
    user_id = user_info.id
    warn_num = await count_user_warn(chat_id, user_id)

    if not warn_num:
        return await message.reply(
            tr(
                "reset_warns.user_has_no_warnings_delete_what_trying_acheive",
                user_mention=user_info.mention,
            )
        )

    await reset_user_warns(chat_id, user_id)
    await message.reply(
        tr(
            "reset_warns.user_has_had_all_their_previous_warns_removed",
            user_mention=user_info.mention,
        )
    )
