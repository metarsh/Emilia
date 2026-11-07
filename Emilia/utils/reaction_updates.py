import re

from pyrogram.enums import ChatMemberStatus

from Emilia.database.approval import is_approved
from Emilia.database.blocklists import get_blocklist
from Emilia.database.federations import get_chat_fed, get_fban_user
from Emilia.database.locks import get_allowlist, get_locks
from Emilia.modules.locks import lock_map
from Emilia.utils.allowlist import sender_is_allowlisted
from Emilia.utils.chat_status import (
    _perm,
    _status,
    get_chat_member_cached,
    has_chat_permission,
    member_is_present,
)

REACTION_LOCK = lock_map.LocksMap.reaction.value
OUTSIDE_REACTION_LOCK = lock_map.LocksMap.outsidereaction.value
GUESTBOT_LOCK = lock_map.LocksMap.guestbot.value


async def _is_chat_member(client, chat_id: int, user_id: int) -> bool:
    member = await get_chat_member_cached(client, chat_id, user_id)
    return member_is_present(member)


async def _is_restricted_from_reactions(client, chat_id: int, user_id: int) -> bool:
    member = await get_chat_member_cached(client, chat_id, user_id)
    if not member or _status(member) != ChatMemberStatus.RESTRICTED:
        return False

    return _perm(member, "can_react_to_messages") is False


async def _handle_message_reaction(client, reaction_update):
    new_reaction = reaction_update.new_reaction or []
    if not new_reaction:
        return

    chat_id = reaction_update.chat.id
    message_id = reaction_update.message_id
    user = reaction_update.user
    actor_chat = reaction_update.actor_chat
    user_id = user.id if user else None
    actor_chat_id = actor_chat.id if actor_chat else None

    locks = await get_locks(chat_id)
    should_delete = False

    if user_id is not None:
        fed_id = await get_chat_fed(chat_id)
        if fed_id:
            is_fbanned, _, _ = await get_fban_user(fed_id, user_id)
            if is_fbanned:
                await client.ban_chat_member(chat_id, user_id)
                await _require_success(
                    client.delete_all_message_reactions(chat_id, user_id=user_id)
                )
                return

        if REACTION_LOCK in locks:
            if not await has_chat_permission(client, chat_id, user_id) and not await is_approved(
                chat_id, user_id, fresh=True
            ):
                should_delete = True

        if OUTSIDE_REACTION_LOCK in locks and not await _is_chat_member(client, chat_id, user_id):
            should_delete = True

        if await _is_restricted_from_reactions(client, chat_id, user_id):
            should_delete = True

    elif actor_chat_id is not None:
        if REACTION_LOCK in locks or OUTSIDE_REACTION_LOCK in locks:
            allowlist = await get_allowlist(chat_id)
            if actor_chat_id not in allowlist:
                should_delete = True

    if should_delete:
        await _require_success(
            client.delete_message_reaction(
                chat_id, message_id, user_id=user_id, actor_chat_id=actor_chat_id
            )
        )


async def _require_success(operation):
    if not await operation:
        raise RuntimeError("Telegram did not complete the reaction removal")


async def enforce_guestbot_lock(message, locks):
    if GUESTBOT_LOCK not in locks or not (
        message.guest_bot_caller_user or message.guest_bot_caller_chat
    ):
        return False
    bot = message.from_user if message.from_user and message.from_user.is_bot else message.via_bot
    allowlist = await get_allowlist(message.chat.id)
    if sender_is_allowlisted(bot, allowlist):
        return False
    await message.delete()
    return True


async def _handle_guest_message(client, message):
    locks = await get_locks(message.chat.id)
    if await enforce_guestbot_lock(message, locks):
        return
    text = message.text or message.caption or ""
    if not text:
        return
    for item in await get_blocklist(message.chat.id):
        trigger = item.get("blocklist_text")
        if not trigger or trigger.startswith("emojipack:"):
            continue
        pattern = r"(?: |^|[^\w])" + re.escape(trigger) + r"(?: |$|[^\w])"
        if re.search(pattern, text, flags=re.IGNORECASE):
            await message.delete()
            return
