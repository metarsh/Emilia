from datetime import UTC, datetime, timedelta

from pyrogram.enums import ChatType

from Emilia.database.warnings import (
    count_user_warn,
    get_all_warn_reason,
    get_warn_mode,
    reset_user_warns,
    warn_limit,
)
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.restrictions import restrict_member


async def warn_checker(client, message, user_id, silent=False):
    chat_id = effective_chat_id(message)
    count = await count_user_warn(chat_id, user_id)
    limit = await warn_limit(chat_id)
    if count < limit:
        return False, "WARN"
    mode, duration = await get_warn_mode(chat_id)
    if mode in {3, 4, 5} and effective_chat(message).type != ChatType.SUPERGROUP:
        await message.reply_text(tr("errors.supergroup_only"))
        return None, ""
    until = datetime.now(UTC) + timedelta(seconds=int(duration or 0))
    if mode == 1:
        await client.ban_chat_member(chat_id, user_id)
        event, text_key = "WARN_BAN", "warn_checker.s_warnings_banned"
    elif mode == 2:
        await client.ban_chat_member(chat_id, user_id)
        await client.unban_chat_member(chat_id, user_id)
        event, text_key = "WARN_KICK", "warn_checker.s_warnings_kicked"
    elif mode == 3:
        await restrict_member(chat_id, user_id, client=client)
        event, text_key = "WARN_MUTE", "warn_checker.s_warnings_muted"
    elif mode == 4:
        await client.ban_chat_member(chat_id, user_id, until_date=until)
        event, text_key = "WARN_TEMP_BAN", "warn_checker.s_warnings_temporarily_banned"
    elif mode == 5:
        await restrict_member(chat_id, user_id, until_date=int(until.timestamp()), client=client)
        event, text_key = "WARN_TEMP_MUTE", "warn_checker.s_warnings_temporarily_muted"
    else:
        return None, ""
    reasons = await get_all_warn_reason(chat_id, user_id)
    await reset_user_warns(chat_id, user_id)
    if not silent:
        user = await client.get_users(user_id)
        await message.reply(
            tr(text_key, countuser_warn=count, warnlimit=limit, user_mention=user.mention)
            + "".join(reasons)
        )
    return True, event
