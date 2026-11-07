import re

from pyrogram import Client, enums, filters

from Emilia.database.approval import is_approved
from Emilia.database.locks import get_allowlist as _get_allowlist_cached
from Emilia.database.locks import get_locks as _get_locks_cached
from Emilia.database.locks import lockwarns_db as _get_lockwarns
from Emilia.locales import tr
from Emilia.modules.locks import lock_map
from Emilia.modules.warnings.warn import warn
from Emilia.utils.allowlist import (
    extract_message_urls,
    is_telegram_invite_url,
    normalize_allowlist_url,
    sender_is_allowlisted,
)
from Emilia.utils.chat_status import (
    check_bot,
    get_chat_member_cached,
    is_user_admin,
    member_is_present,
)
from Emilia.utils.custom_emoji import extract_emojipack_tokens
from Emilia.utils.forward_origin import fwd_chat, fwd_date, fwd_user
from Emilia.utils.linked_chat import is_linked_forward
from Emilia.utils.message_actor import actor_id, actor_user, sender_entity
from Emilia.utils.reaction_updates import enforce_guestbot_lock

PHONE_REGEX = re.compile(r"[\+\(]?[1-9][0-9 .\-\(\)]{8,}[0-9]")
EMAIL_REGEX = re.compile(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", re.IGNORECASE)
# RTL heuristic: any char within known RTL unicode ranges (excluding variation selectors like U+FE0F)
RTL_CHAR_REGEX = re.compile(r"[\u0590-\u08FF\uFB1D-\uFDFD\uFE70-\uFEFC]")


@Client.on_message(
    filters.all & (filters.group | filters.channel) | filters.new_chat_members, group=4
)
async def locks_checker(client, message):
    chat_id = message.chat.id
    LOCKS_LIST = await _get_locks_cached(chat_id)
    if len(LOCKS_LIST) == 0:
        return

    if 2 in LOCKS_LIST:
        if message.media_group_id:
            return await lock_action(client, message, action=2)

    if 3 in LOCKS_LIST:
        if message.audio:
            return await lock_action(client, message, action=3)

    if 4 in LOCKS_LIST:
        new_bots = [
            member for member in (message.new_chat_members or []) if member and member.is_bot
        ]
        if new_bots:
            if await is_user_admin(message, silent=True):
                return
            if not await check_bot(
                message, privileges=["can_delete_messages", "can_restrict_members"]
            ):
                return
            if actor_user(message) is not None and await _get_lockwarns(chat_id):
                reason = tr("locks_checker.bot_locked_chat")
                await warn(client, message, reason, warn_user=message)
            for new_bot in new_bots:
                await client.ban_chat_member(chat_id, new_bot.id)
                await client.unban_chat_member(chat_id, new_bot.id)
            await message.delete()
            return

    if 5 in LOCKS_LIST:
        if message.reply_markup:
            return await lock_action(client, message, action=5)

    if 6 in LOCKS_LIST:
        if any(
            entity.type == enums.MessageEntityType.BOT_COMMAND and entity.offset == 0
            for entity in message.entities or []
        ):
            return await lock_action(client, message, action=6)

    if 7 in LOCKS_LIST:
        user = actor_user(message)
        if user is not None and await is_linked_forward(client, message.reply_to_message):
            member = await get_chat_member_cached(client, chat_id, user.id, fresh=True)
            if not member_is_present(member):
                if await check_bot(message, privileges="can_delete_messages", silent=True):
                    await message.delete()
                    return

    if 8 in LOCKS_LIST:
        if message.contact:
            return await lock_action(client, message, action=8)

    if 9 in LOCKS_LIST:
        if message.document:
            return await lock_action(client, message, action=9)

    if 10 in LOCKS_LIST:
        if EMAIL_REGEX.search(message.text or message.caption or ""):
            return await lock_action(client, message, action=10)

    if 11 in LOCKS_LIST:
        if message.dice:
            return await lock_action(client, message, action=11)

    if 12 in LOCKS_LIST:
        if fwd_date(message):
            ALLOW_LIST = await _get_allowlist_cached(chat_id)
            if not sender_is_allowlisted(sender_entity(message), ALLOW_LIST):
                return await lock_action(client, message, action=12)

    if 13 in LOCKS_LIST:
        fwd_user_13 = fwd_user(message)
        if fwd_user_13 and fwd_user_13.is_bot:
            return await lock_action(client, message, action=13)

    if 14 in LOCKS_LIST:
        fwd_chat_14 = fwd_chat(message)
        if fwd_chat_14 and fwd_chat_14.type == enums.ChatType.CHANNEL:
            ALLOW_LIST = await _get_allowlist_cached(chat_id)
            if not sender_is_allowlisted(fwd_chat_14, ALLOW_LIST):
                return await lock_action(client, message, action=14)

    if 15 in LOCKS_LIST:
        fwd_user_15 = fwd_user(message)
        if fwd_user_15 and not fwd_user_15.is_bot:
            return await lock_action(client, message, action=15)

    if 16 in LOCKS_LIST:
        if message.game:
            return await lock_action(client, message, action=16)

    if 17 in LOCKS_LIST:
        if message.animation:
            return await lock_action(client, message, action=17)

    if 18 in LOCKS_LIST:
        if message.via_bot:
            ALLOW_LIST = await _get_allowlist_cached(chat_id)
            if not sender_is_allowlisted(message.via_bot, ALLOW_LIST):
                return await lock_action(client, message, action=18)

    if 19 in LOCKS_LIST:
        if any(is_telegram_invite_url(url) for url in extract_message_urls(message)):
            return await lock_action(client, message, action=19)

    if 20 in LOCKS_LIST:
        if message.location:
            return await lock_action(client, message, action=20)

    if 21 in LOCKS_LIST:
        if message.text or message.caption:
            text = message.text or message.caption
            PHONE_NOs_LIST = PHONE_REGEX.findall(text)

            if len(PHONE_NOs_LIST) != 0:
                return await lock_action(client, message, action=21)

    if 22 in LOCKS_LIST:
        if message.photo:
            return await lock_action(client, message, action=22)

    if 23 in LOCKS_LIST:
        if message.poll:
            return await lock_action(client, message, action=23)

    if 24 in LOCKS_LIST:
        text = message.text or message.caption

        if text:
            if RTL_CHAR_REGEX.search(text) and not text.isdigit():
                return await lock_action(client, message, action=24)

    if 25 in LOCKS_LIST:
        if message.sticker:
            return await lock_action(client, message, action=25)

    if 26 in LOCKS_LIST:
        if message.text or message.caption:
            return await lock_action(client, message, action=26)

    if 27 in LOCKS_LIST:
        text = message.text or message.caption

        if text:
            URL_LIST = extract_message_urls(message)
            if len(URL_LIST) != 0:
                ALLOW_LIST = await _get_allowlist_cached(chat_id)
                if len(ALLOW_LIST) != 0:
                    allowed_urls = {
                        normalize_allowlist_url(item)
                        for item in ALLOW_LIST
                        if isinstance(item, str)
                    }
                    for url in URL_LIST:
                        if normalize_allowlist_url(url) not in allowed_urls:
                            return await lock_action(client, message, action=27)
                else:
                    return await lock_action(client, message, action=27)

    if 28 in LOCKS_LIST:
        if message.video:
            return await lock_action(client, message, action=28)

    if 29 in LOCKS_LIST:
        if message.video_note:
            return await lock_action(client, message, action=29)

    if 30 in LOCKS_LIST:
        if message.voice:
            return await lock_action(client, message, action=30)

    if lock_map.LocksMap.emojicustom.value in LOCKS_LIST:
        emojipacks = await extract_emojipack_tokens(client, message)
        if emojipacks:
            ALLOW_LIST = set(await _get_allowlist_cached(chat_id))
            if not ALLOW_LIST or any(pack not in ALLOW_LIST for pack in emojipacks):
                return await lock_action(
                    client, message, action=lock_map.LocksMap.emojicustom.value
                )

    if await enforce_guestbot_lock(message, LOCKS_LIST):
        return

    if (
        lock_map.LocksMap.spoiler.value in LOCKS_LIST
        or lock_map.LocksMap.format.value in LOCKS_LIST
        or lock_map.LocksMap.code.value in LOCKS_LIST
    ):
        entities = []
        if message.entities:
            entities.extend(message.entities)
        if message.caption_entities:
            entities.extend(message.caption_entities)

        if entities:
            has_spoiler = False
            has_format = False
            has_code = False

            for ent in entities:
                if ent.type == enums.MessageEntityType.SPOILER:
                    has_spoiler = True
                elif ent.type in {
                    enums.MessageEntityType.BOLD,
                    enums.MessageEntityType.ITALIC,
                    enums.MessageEntityType.UNDERLINE,
                    enums.MessageEntityType.STRIKETHROUGH,
                    enums.MessageEntityType.BLOCKQUOTE,
                }:
                    has_format = True
                elif ent.type in {enums.MessageEntityType.CODE, enums.MessageEntityType.PRE}:
                    has_code = True

            if has_spoiler and lock_map.LocksMap.spoiler.value in LOCKS_LIST:
                return await lock_action(client, message, action=lock_map.LocksMap.spoiler.value)
            elif has_format and lock_map.LocksMap.format.value in LOCKS_LIST:
                return await lock_action(client, message, action=lock_map.LocksMap.format.value)
            elif has_code and lock_map.LocksMap.code.value in LOCKS_LIST:
                return await lock_action(client, message, action=lock_map.LocksMap.code.value)


async def lock_action(client, message, action: int = None, delete: bool = True):
    lock_name = lock_map.LocksMap(action).name
    if await is_user_admin(message, silent=True):
        return
    uid = actor_id(message)
    if await is_approved(message.chat.id, uid):
        return
    if not await check_bot(message, privileges="can_delete_messages", silent=True):
        return
    if (
        actor_user(message) is not None
        and await _get_lockwarns(message.chat.id)
        and await check_bot(message, privileges="can_restrict_members", silent=True)
    ):
        reason = tr("locks_checker.locked_chat", lock_name=lock_name)
        await warn(client, message, reason, warn_user=message)
    if delete:
        await message.delete()
