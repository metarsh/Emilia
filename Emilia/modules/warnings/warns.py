from Emilia.custom_filter import command
from Emilia.database.warnings import count_user_warn, get_all_warn_reason, warn_limit
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.get_user import get_user_id
from Emilia.utils.message_actor import actor_user


@command("warns", disable=True, chat_scope="group", allow_connected=True)
@anonadmin_checker
async def warns(client, message):
    chat_id = effective_chat_id(message)

    is_admin = await is_user_admin(message, silent=True)

    if is_admin and len(message.text.split()) >= 2:
        user_info = await get_user_id(message)
    else:
        if len(message.text.split()) >= 2 and not is_admin:
            return await message.reply(tr("warns.only_admins_can_check_another_user_s"))
        user_info = actor_user(message)

    if not user_info:
        return
    user_id = user_info.id

    user_warn_num = await count_user_warn(chat_id, user_id)
    if user_warn_num is None or user_warn_num == 0:
        return await message.reply(tr("warns.user_has_no_warnings", user_mention=user_info.mention))

    chat_warn_limit = await warn_limit(chat_id)
    REASONS = await get_all_warn_reason(chat_id, user_id)

    await message.reply(
        tr(
            "warns.user_has_warnings_reasons",
            user_mention=user_info.mention,
            user_warn_num=user_warn_num,
            chat_warn_limit=chat_warn_limit,
            reasons="".join(REASONS),
        )
    )
