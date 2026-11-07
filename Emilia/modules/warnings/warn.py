from pyrogram.enums import ButtonStyle

from Emilia.database.warnings import count_user_warn, warn_db, warn_limit
from Emilia.locales import tr
from Emilia.modules.warnings.warn_checker import warn_checker
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import can_restrict_member
from Emilia.utils.client_context import bot_id, bot_name
from Emilia.utils.confirmation import send_confirmation
from Emilia.utils.get_user import get_user_id, mention_html
from Emilia.utils.message_actor import actor_id, actor_name, actor_user


async def warn(client, message, reason, silent=False, warn_user=None):
    chat_id = effective_chat_id(message)

    admin_id = bot_id(client) if warn_user is not None else actor_id(message)
    if admin_id is None:
        return False, None, None

    if warn_user is None:
        user_info = await get_user_id(message)
        if user_info is None:
            return False, None, None
    else:
        user_info = actor_user(warn_user)
        if user_info is None:
            return False, None, None

    user_id = user_info.id
    if user_id == bot_id(client):
        if warn_user is None:
            await message.reply(tr("warn.bold_of_you_to_think_i_m"))
        return False, None, None
    if not await can_restrict_member(message, user_id):
        if warn_user is None:
            await message.reply(tr("warn.wish_i_could_warn_an_admin_but"))
        return False, None, None

    warning_id = await warn_db(chat_id, admin_id, user_id, reason)
    warnchecker, log_msg = await warn_checker(client, message, user_id, silent)

    if (warnchecker is True) or (warnchecker is None):
        return False, log_msg, None

    countuser_warn = await count_user_warn(chat_id, user_id)
    warnlimit = await warn_limit(chat_id)

    import html

    actor_html = (
        tr("warn.admin", admin_id=admin_id)
        if admin_id < 0
        else mention_html(
            admin_id,
            bot_name(client) if warn_user is not None else actor_name(message),
            client=client,
        )
    )
    target_html = mention_html(user_id, user_info.first_name, client=client)

    warn_text = tr(
        "warn.yep_has_warned_count",
        target_html=target_html,
        actor_html=actor_html,
        countuser_warn=countuser_warn,
        warnlimit=warnlimit,
    )
    if reason:
        warn_text += tr("bans.execute_operation_reason", reason=html.escape(reason))

    if not silent:
        await send_confirmation(
            message,
            warn_text,
            "remove_warn",
            {"chat_id": chat_id, "user_id": user_id, "warning_id": warning_id},
            [("warnrm", tr("warn.remove_warn_admin_only"), ButtonStyle.DANGER)],
            client=client,
        )
    return True, log_msg, user_info
