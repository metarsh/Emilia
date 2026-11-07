import re
import time
from asyncio import sleep
from datetime import datetime, timedelta

from Emilia.database.blocklists import (
    get_blocklist_reason,
    getblocklistMessageDelete,
    getblocklistmode,
)
from Emilia.locales import tr
from Emilia.modules.warnings.warn import warn
from Emilia.utils.chat_status import bot_has_permission
from Emilia.utils.decorators import log_to_channel
from Emilia.utils.message_actor import actor_user
from Emilia.utils.restrictions import restrict_member
from Emilia.utils.time import convert_time

_ACTION_TAG_RE = re.compile(r"\{([^{}]+)\}")


def _parse_time_token_to_seconds(time_token: str) -> int | None:
    """Parse a compact duration like 6h/3d/4m/5w into seconds."""

    if not time_token:
        return None

    m = re.fullmatch(r"([0-9]{1,8})([wdhmWDHM])", time_token.strip())
    if not m:
        return None

    amount = int(m.group(1))
    unit = m.group(2).lower()
    if amount <= 0:
        return None

    seconds = convert_time(amount, unit)
    # 31622400 seconds is 366 days.
    if seconds >= 31622400:
        return None
    return int(seconds)


def _extract_override_from_reason(
    reason: str | None,
) -> tuple[int | None, int | None, str | None]:
    """Extract per-blocklist action override from reason text.

    Supports tags: {warn}, {mute}, {ban}, {kick}, {tban 6h}, {tmute 6h}.
    """

    if not reason:
        return None, None, reason

    override_mode = None
    override_time = None

    for raw in _ACTION_TAG_RE.findall(reason):
        parts = raw.strip().split()
        if not parts:
            continue
        action = parts[0].lower()
        time_token = parts[1] if len(parts) >= 2 else None

        if action == "warn":
            override_mode, override_time = 5, None
        elif action == "ban":
            override_mode, override_time = 2, None
        elif action == "mute":
            override_mode, override_time = 3, None
        elif action == "kick":
            override_mode, override_time = 4, None
        elif action == "tban":
            secs = _parse_time_token_to_seconds(time_token or "")
            if secs is not None:
                override_mode, override_time = 6, secs
        elif action == "tmute":
            secs = _parse_time_token_to_seconds(time_token or "")
            if secs is not None:
                override_mode, override_time = 7, secs

    # Strip recognized tags from the visible reason
    def _strip_tag(m: re.Match) -> str:
        inner = m.group(1).strip().lower()
        head = inner.split()[0] if inner else ""
        return "" if head in {"warn", "ban", "mute", "kick", "tban", "tmute"} else m.group(0)

    cleaned = _ACTION_TAG_RE.sub(_strip_tag, reason)
    cleaned = " ".join(cleaned.split()).strip() or None
    return override_mode, override_time, cleaned


@log_to_channel
async def blocklist_action(client, message, blocklist_word):
    chat_id = message.chat.id
    if actor_user(message) is None:
        # Can't apply admin actions to sender chats (channels); just delete if
        # enabled.
        if await getblocklistMessageDelete(chat_id) and await bot_has_permission(
            message, privileges="can_delete_messages", silent=True
        ):
            await message.delete()
        return

    user_id = message.from_user.id

    reason = await get_blocklist_reason(chat_id, blocklist_word)
    override_mode, override_time, cleaned_reason = _extract_override_from_reason(reason)

    blocklist_mode, blocklist_time, dreason = await getblocklistmode(chat_id)

    # Choose reason text (override tag removed) or fall back to default.
    if cleaned_reason is not None:
        reason = cleaned_reason
    else:
        if dreason is None:
            reason = tr(
                "checker.automated_blocklist_action_due_match", blocklist_word=blocklist_word
            )
        else:
            reason = dreason

    # Override per-filter action if present; otherwise use chat-level mode.
    action_mode = override_mode if override_mode is not None else blocklist_mode
    action_time = override_time if override_mode is not None else blocklist_time

    if action_mode == 1:
        if await getblocklistMessageDelete(chat_id):
            await message.delete()
        return

    elif action_mode == 2:
        await client.ban_chat_member(chat_id, user_id)
        await message.reply(
            tr(
                "checker.user_banned_reason",
                user_mention=message.from_user.mention,
                reason=reason,
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()

        return "BLOCKLIST_BAN", user_id, message.from_user.first_name

    elif action_mode == 3:
        await restrict_member(chat_id, user_id, client=client)
        await message.reply(
            tr(
                "checker.user_muted_now_reason",
                user_mention=message.from_user.mention,
                reason=reason,
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()

        return "BLOCKLIST_MUTE", user_id, message.from_user.first_name

    elif action_mode == 4:
        await client.ban_chat_member(
            chat_id,
            user_id,
            # wait 60 seconds in case of server goes down at unbanning time
            int(time.time()) + 60,
        )
        await message.reply(
            tr(
                "checker.user_has_kicked_reason",
                user_mention=message.from_user.mention,
                reason=reason,
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()

        # Unbanning proceess and wait 5 sec to give server to kick user first
        await sleep(5)
        await client.unban_chat_member(chat_id, user_id)
        return "BLOCKLIST_KICK", user_id, message.from_user.first_name

    elif action_mode == 5:
        await warn(client, message, reason, warn_user=message)

        if await getblocklistMessageDelete(chat_id):
            await message.delete()

    elif action_mode == 6:
        if not action_time:
            # If time is missing/invalid, fall back to permanent ban.
            await client.ban_chat_member(chat_id, user_id)
            await message.reply(
                tr(
                    "checker.user_banned_reason",
                    user_mention=message.from_user.mention,
                    reason=reason,
                )
            )
            if await getblocklistMessageDelete(chat_id):
                await message.delete()
            return "BLOCKLIST_BAN", user_id, message.from_user.first_name

        until_date = datetime.now() + timedelta(seconds=int(action_time))
        await client.ban_chat_member(chat_id=chat_id, user_id=user_id, until_date=until_date)
        await message.reply(
            tr(
                "checker.user_temporarily_banned_reason",
                user_mention=message.from_user.mention,
                reason=reason,
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()
        return "BLOCKLIST_TEMPBAN", user_id, message.from_user.first_name

    elif action_mode == 7:
        if not action_time:
            # If time is missing/invalid, fall back to permanent mute.
            await restrict_member(chat_id, user_id, client=client)
            await message.reply(
                tr(
                    "checker.user_muted_now_reason",
                    user_mention=message.from_user.mention,
                    reason=reason,
                )
            )
            if await getblocklistMessageDelete(chat_id):
                await message.delete()
            return "BLOCKLIST_MUTE", user_id, message.from_user.first_name

        until_date = datetime.now() + timedelta(seconds=int(action_time))
        until_ts = int(until_date.timestamp())
        await restrict_member(chat_id, user_id, until_date=until_ts, client=client)
        await message.reply(
            tr(
                "checker.user_temporarily_muted_reason",
                user_mention=message.from_user.mention,
                reason=reason,
            )
        )

        if await getblocklistMessageDelete(chat_id):
            await message.delete()
        return "BLOCKLIST_TEMPMUTE", user_id, message.from_user.first_name
