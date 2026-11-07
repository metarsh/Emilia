import asyncio
import os
import time

from pymongo.errors import PyMongoError
from pyrogram.enums import (
    ChatMembersFilter,
    ChatMemberStatus,
    ChatType,
    ParseMode,
    UserStatus,
)
from pyrogram.errors import (
    ChatAdminRequired,
    FloodWait,
    MessageDeleteForbidden,
    RPCError,
    UserAdminInvalid,
)
from pyrogram.raw import functions as raw_functions
from pyrogram.raw import types as raw_types
from pyrogram.types import ChatPrivileges
from redis.exceptions import RedisError

from Emilia.application import LOGGER
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.admins import cache_collection, get_user_reason, update_admin_cache
from Emilia.utils.auth import is_dev
from Emilia.utils.cache import SimpleCache
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_user, has_chat_permission, is_user_admin, member_is_admin
from Emilia.utils.client_context import bot_id
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import (
    _invalidate_admin_caches,
    anonadmin_checker,
    log_to_channel,
)
from Emilia.utils.errors import telegram_error_text
from Emilia.utils.message_actor import actor_id
from Emilia.utils.tg_safe import flood_safe


def _is_group(message):
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


# Telegram enforces a 16-char max on custom admin titles.
ADMIN_TITLE_MAX = 16


def _clamp_title(title):
    if title and len(title) > ADMIN_TITLE_MAX:
        return title[:ADMIN_TITLE_MAX]
    return title


# ChatPrivileges with every flag False, used for demotes.
DEMOTE_RIGHTS = ChatPrivileges(
    can_manage_chat=False,
    can_delete_messages=False,
    can_manage_video_chats=False,
    can_restrict_members=False,
    can_promote_members=False,
    can_change_info=False,
    can_invite_users=False,
    can_pin_messages=False,
    is_anonymous=False,
)


@command("promote", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def promote(client, promt):
    chat_id = effective_chat_id(promt)
    users, title = await get_user_reason(promt)
    if not users:
        return await promt.reply_text(tr("errors.user_not_found"))
    elif await is_user_admin(promt, chat_id=chat_id, user_id=users.id, silent=True):
        return await promt.reply_text(tr("permissions.cannot_target_admin"))
    elif not await check_user(
        promt, chat_id=chat_id, user_id=actor_id(promt), privileges="can_promote_members"
    ):
        return
    new_rights = ChatPrivileges(
        can_invite_users=True,
        can_change_info=True,
        can_restrict_members=False,
        can_delete_messages=True,
        can_pin_messages=True,
    )

    await client.promote_chat_member(chat_id, users.id, privileges=new_rights)
    await client.set_administrator_title(
        chat_id, users.id, _clamp_title(title) if title else "Admin"
    )
    await _invalidate_admin_caches(chat_id, users.id, client=client)
    await _adminlist_cache.delete(f"list:{bot_id(client)}:{chat_id}")
    await update_admin_cache(chat_id, users.id, True, client=client)
    await promt.reply_text(tr("admin.promoted_successfully", user_name=users.first_name))
    return "PROMOTE", users.id, users.first_name


@command("fullpromote", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def fpromote(client, promt):
    chat_id = effective_chat_id(promt)
    users, title = await get_user_reason(promt)
    if not users:
        return await promt.reply_text(tr("errors.user_not_found"))
    elif await is_user_admin(promt, chat_id=chat_id, user_id=users.id, silent=True):
        return await promt.reply_text(tr("permissions.cannot_target_admin"))
    elif not await check_user(
        promt, chat_id=chat_id, user_id=actor_id(promt), privileges="can_promote_members"
    ):
        return
    new_rights = ChatPrivileges(
        can_promote_members=True,
        can_invite_users=True,
        can_change_info=True,
        can_restrict_members=True,
        can_delete_messages=True,
        can_pin_messages=True,
        can_manage_video_chats=True,
    )
    await client.promote_chat_member(chat_id, users.id, privileges=new_rights)
    await client.set_administrator_title(
        chat_id, users.id, _clamp_title(title) if title else "Admin"
    )
    await _invalidate_admin_caches(chat_id, users.id, client=client)
    await _adminlist_cache.delete(f"list:{bot_id(client)}:{chat_id}")
    await update_admin_cache(chat_id, users.id, True, client=client)
    await promt.reply_text(
        tr("admin.promoted_full_rights_successfully", user_name=users.first_name)
    )
    return "FULL_PROMOTE", users.id, users.first_name


@command("admincache", chat_scope="group", allow_connected=True)
async def admincach(client, event):
    chat_id = effective_chat_id(event)

    try:
        async for stale in cache_collection.find({"chat_id": chat_id, "is_admin": True}):
            await _invalidate_admin_caches(chat_id, stale["user_id"], client=client)
    except (PyMongoError, RedisError):
        LOGGER.warning("admincache stale-entry invalidation failed", exc_info=True)

    # Clear existing cache for this chat to avoid stale entries
    try:
        await cache_collection.delete_many({"chat_id": chat_id})
    except PyMongoError:
        # Best-effort; continue even if delete fails
        LOGGER.warning("admincache delete_many failed", exc_info=True)

    # Fetch current admins and repopulate cache with accurate True flags
    async for i in client.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
        await _invalidate_admin_caches(chat_id, i.user.id, client=client)
        await update_admin_cache(chat_id, i.user.id, True, client=client)
    await _adminlist_cache.delete(f"list:{bot_id(client)}:{chat_id}")
    await event.reply_text(tr("admin.admin_cache_refreshed"))


@command("demote", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def demote(client, dmod):
    chat_id = effective_chat_id(dmod)
    users, _ = await get_user_reason(dmod)
    if not users:
        return await dmod.reply_text(tr("errors.user_not_found"))
    elif not await is_user_admin(dmod, chat_id=chat_id, user_id=users.id, silent=True):
        return await dmod.reply_text(tr("permissions.target_must_be_admin"))
    elif not await check_user(
        dmod, chat_id=chat_id, user_id=actor_id(dmod), privileges="can_promote_members"
    ):
        return

    # Only group owner (or dev users) can demote an admin with
    # can_promote_members; regular admins shouldn't demote each other.
    target_member = await client.get_chat_member(chat_id, users.id)
    if (
        target_member.status == ChatMemberStatus.ADMINISTRATOR
        and target_member.privileges.can_promote_members
    ):
        if not await has_chat_permission(client, chat_id, actor_id(dmod), owner=True):
            return await dmod.reply_text(tr("permissions.owner_required"))

    await client.promote_chat_member(chat_id, users.id, privileges=DEMOTE_RIGHTS)
    await _invalidate_admin_caches(chat_id, users.id, client=client)
    await _adminlist_cache.delete(f"list:{bot_id(client)}:{chat_id}")
    await update_admin_cache(chat_id, users.id, False, client=client)
    await dmod.reply_text(tr("admin.demoted_successfully", user_name=users.first_name))
    return "DEMOTE", users.id, users.first_name


_adminlist_cache = SimpleCache(default_ttl=120, namespace="adminlist")


@command(pattern="admins|adminlist", chat_scope="group", allow_connected=True)
async def get_admin(client, show):
    chat_id = effective_chat_id(show)
    title = effective_chat(show).title

    cache_key = f"list:{bot_id(client)}:{chat_id}"
    mentions = await _adminlist_cache.get(cache_key)
    if mentions is None:
        admins = []
        bots = []
        async for admin in client.get_chat_members(
            chat_id, filter=ChatMembersFilter.ADMINISTRATORS
        ):
            admins.append(admin.user)
            if admin.user.is_bot:
                bots.append(admin.user)

        mentions = tr("admin.admins", title=title)
        mentions += "\n".join(
            tr(
                "admin.get_admin_user_id_user_name_user_id_2",
                user_id=admin.id,
                user_name=admin.first_name,
                user_id_2=admin.id,
            )
            for admin in admins
        )
        mentions += tr("admin.total_admins", admins=len(admins))
        mentions += tr("admin.total_bots", bots=len(bots))
        await _adminlist_cache.set(cache_key, mentions, ttl=120)

    await show.reply_text(mentions, parse_mode=ParseMode.HTML)


@command("setgpic", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def set_group_photo(client, gpic):
    replymsg = gpic.reply_to_message
    photo = None
    chat_id = effective_chat_id(gpic)
    if not await check_user(
        gpic, chat_id=chat_id, user_id=actor_id(gpic), privileges="can_change_info"
    ):
        return
    elif not replymsg:
        return await reply_usage(gpic)
    if replymsg and replymsg.media:
        if replymsg.photo:
            photo = await replymsg.download()
        elif replymsg.document and "image" in replymsg.document.mime_type.split("/"):
            photo = await replymsg.download()
        else:
            await gpic.reply_text(tr("errors.invalid_media"))
    if photo:
        await client.set_chat_photo(chat_id, photo=photo)
        os.remove(photo)
        await gpic.reply_text(tr("admin.successfully_changed_group_profile_photo"))
        return "NEW_GPIC", None, None


@command("title", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def settitle(client, promt):
    user, title_admin = await get_user_reason(promt)
    chat_id = effective_chat_id(promt)
    if not await check_user(
        promt, chat_id=chat_id, user_id=actor_id(promt), privileges="can_promote_members"
    ):
        return
    elif not user:
        return await reply_usage(promt)
    elif not title_admin:
        return await reply_usage(promt)
    elif not await is_user_admin(promt, chat_id=chat_id, user_id=user.id, silent=True):
        return await promt.reply_text(tr("permissions.target_must_be_admin"))
    title_admin = _clamp_title(title_admin)
    # set_administrator_title keeps the existing admin rights
    await client.set_administrator_title(chat_id, user.id, title_admin)
    await promt.reply_text(
        tr("admin.title_set_successfully", user_name=user.first_name, title_admin=title_admin)
    )
    return "NEW_TITLE", user.id, user.first_name


@command("zombies", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def rm_deletedacc(client, show):
    chat_id = effective_chat_id(show)
    con = show.command[1].lower() if len(show.command) > 1 else ""
    del_u = 0
    del_status = tr("admin.no_deleted_accounts_found_group_clean")
    if not await check_user(show, user_id=actor_id(show), privileges="can_restrict_members"):
        return
    if con != "clean":
        await show.reply_text(tr("admin.searching_for_zombie_accounts"))
        async for member in client.get_chat_members(chat_id):
            if member.user.is_deleted:
                del_u += 1
        if del_u > 0:
            del_status = tr("admin.found_deleted_account_s_group_clean_them_using", del_u=del_u)
        return await show.reply_text(del_status)
    await show.reply_text(tr("admin.banning_deleted_accounts"))
    del_u = 0
    del_a = 0
    async for member in client.get_chat_members(chat_id):
        # pace mass iteration under Telegram's ceiling
        await asyncio.sleep(0.05)
        if member.user.is_deleted:
            if member_is_admin(member) or is_dev(member.user.id):
                del_a += 1
                continue
            try:
                await flood_safe(
                    lambda user_id=member.user.id: client.ban_chat_member(chat_id, user_id)
                )
            except ChatAdminRequired:
                return await show.reply_text(tr("permissions.bot_ban_required"))
            except UserAdminInvalid:
                del_a += 1
                continue
            await flood_safe(
                lambda user_id=member.user.id: client.unban_chat_member(chat_id, user_id)
            )
            del_u += 1
    if del_u > 0:
        del_status = tr("admin.cleaned_deleted_account_s", del_u=del_u)

    if del_a > 0:
        del_status = tr(
            "admin.cleaned_deleted_account_s_deleted_admin_accounts_not", del_u=del_u, del_a=del_a
        )
    await show.reply_text(del_status)
    return "CLEANED_ZOMBIES", None, None


@command("kickdead", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def kickdead(client, event):
    chat_id = effective_chat_id(event)
    if not await check_user(event, user_id=actor_id(event), privileges="can_restrict_members"):
        return
    c = 0
    cnt = 0
    done = await event.reply_text(tr("admin.searching_for_dead_accounts"))
    async for i in client.get_chat_members(chat_id):
        if member_is_admin(i) or is_dev(i.user.id):
            continue
        # pace mass iteration under Telegram's ceiling
        await asyncio.sleep(0.05)
        try:
            if i.user.status == UserStatus.LONG_AGO:
                status = await flood_safe(
                    lambda user_id=i.user.id: client.ban_chat_member(chat_id, user_id)
                )
                await flood_safe(
                    lambda user_id=i.user.id: client.unban_chat_member(chat_id, user_id)
                )
                if not status:
                    return
                c = c + 1
        except UserAdminInvalid:
            cnt += 1
            continue
    if c == 0:
        return await done.edit_text(tr("admin.got_no_one_to_kick"))
    required_string = tr("admin.successfully_kicked_users_who_were_inactive_month_more")
    await done.edit_text(required_string.format(c, cnt))
    return "KICKED_DEAD", None, None


@command("unbanall", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def unbanall(client, event):
    chat_id = effective_chat_id(event)
    if not await check_user(event, user_id=actor_id(event), privileges="can_restrict_members"):
        return
    done = await event.reply_text(tr("admin.searching_for_banned_accounts"))
    p = 0
    async for i in client.get_chat_members(chat_id, filter=ChatMembersFilter.BANNED):
        # pace mass iteration under Telegram's ceiling
        await asyncio.sleep(0.05)
        peer = i.user or i.chat
        if peer is None:
            continue
        await flood_safe(lambda peer_id=peer.id: client.unban_chat_member(chat_id, peer_id))
        p += 1
    if p == 0:
        await done.edit_text(tr("admin.no_one_is_banned_in_this_chat"))
        return
    required_string = tr("admin.successfully_unbanned_users")
    await done.edit_text(required_string.format(p))
    return "UNBANNED_ALL", None, None


@command("unmuteall", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def unmuteall(client, event):
    chat_id = effective_chat_id(event)
    if not await check_user(event, user_id=actor_id(event), privileges="can_restrict_members"):
        return
    done = await event.reply_text(tr("admin.searching_for_muted_accounts"))
    p = 0
    default_permissions = (await client.get_chat(chat_id)).permissions
    async for i in client.get_chat_members(chat_id, filter=ChatMembersFilter.RESTRICTED):
        if i.status != ChatMemberStatus.RESTRICTED or not i.is_member or i.user is None:
            continue
        # pace mass iteration under Telegram's ceiling
        await asyncio.sleep(0.05)
        await flood_safe(
            lambda user_id=i.user.id: client.restrict_chat_member(
                chat_id, user_id, default_permissions
            )
        )
        p += 1
    if p == 0:
        await done.edit_text(tr("admin.no_one_is_muted_in_this_chat"))
        return
    required_string = tr("admin.successfully_unmuted_users")
    await done.edit_text(required_string.format(p))
    return "UNMUTED_ALL", None, None


@command("setgtitle", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def set_group_title(client, gpic):
    input_str = gpic.matches[0].group(1)
    chat_id = effective_chat_id(gpic)
    if not input_str:
        return await reply_usage(gpic)
    if len(input_str) > 255:
        return await gpic.reply_text(tr("admin.title_is_too_long"))
    elif not await check_user(
        gpic, chat_id=chat_id, user_id=actor_id(gpic), privileges="can_change_info"
    ):
        return
    try:
        await client.set_chat_title(chat_id, input_str)
        await gpic.reply_text(tr("admin.group_name_updated_successfully", input_str=input_str))
    except ChatAdminRequired:
        return await gpic.reply_text(tr("permissions.bot_change_info_required"))
    return "NEW_GTITLE", None, None


@command("setdesc", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def set_group_des(client, gpic):
    input_str = gpic.matches[0].group(1)
    chat_id = effective_chat_id(gpic)
    if not input_str:
        return await reply_usage(gpic)
    elif not await check_user(
        gpic, chat_id=chat_id, user_id=actor_id(gpic), privileges="can_change_info"
    ):
        return
    await client.set_chat_description(chat_id, input_str)
    await gpic.reply_text(tr("admin.successfully_set_new_group_description"))
    return "NEW_GDESC", None, None


@command("setsticker", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def set_group_sticker(client, gpic):
    chat_id = effective_chat_id(gpic)
    if not await check_user(gpic, user_id=actor_id(gpic), privileges="can_change_info"):
        return
    rep_msg = gpic.reply_to_message
    if not rep_msg or not rep_msg.sticker:
        return await reply_usage(gpic)
    if not rep_msg.sticker.set_name:
        return await gpic.reply_text(tr("admin.this_sticker_is_not_part_of_any"))
    # Kurigram exposes group sticker packs through raw channels.SetStickers.
    await client.invoke(
        raw_functions.channels.SetStickers(
            channel=await client.resolve_peer(chat_id),
            stickerset=raw_types.InputStickerSetShortName(short_name=rep_msg.sticker.set_name),
        )
    )
    await gpic.reply_text(tr("admin.successfully_set_group_sticker"))
    return "NEW_GSTICKER", None, None


PURGE = {}


MAX_PURGE_MESSAGES = 5000


async def _delete_batch(client, chat_id, msgs):
    try:
        await client.delete_messages(chat_id, msgs)
    except FloodWait as ex:
        await asyncio.sleep(ex.value)
        await _delete_batch(client, chat_id, msgs)
    except MessageDeleteForbidden:
        if len(msgs) == 1:
            return
        for m_id in msgs:
            try:
                await client.delete_messages(chat_id, m_id)
            except FloodWait as ex:
                await asyncio.sleep(ex.value)
                try:
                    await client.delete_messages(chat_id, m_id)
                except MessageDeleteForbidden:
                    pass
            except MessageDeleteForbidden:
                pass


@command("purgefrom")
@anonadmin_checker
async def purge_from(client, event):
    msg = event.reply_to_message
    if not msg:
        return await reply_usage(event)
    if not await check_user(
        event, user_id=actor_id(event), privileges="can_delete_messages"
    ) and _is_group(event):
        return
    PURGE[(bot_id(client), event.chat.id)] = event.reply_to_message_id
    await event.reply_text(tr("admin.purge_from", reply_to_message_id=event.reply_to_message_id))


@command("purgeto")
@anonadmin_checker
async def purge_to(client, event):
    msg = event.reply_to_message
    if not msg:
        return await reply_usage(event)
    if not await check_user(
        event, user_id=actor_id(event), privileges="can_delete_messages"
    ) and _is_group(event):
        return
    try:
        purge_from = PURGE[(bot_id(client), event.chat.id)]
    except KeyError:
        return await event.reply_text(tr("admin.purge_from_not_found"))
    reply = event.reply_to_message
    if not reply:
        return await reply_usage(event)
    purge_to = reply.id
    total = purge_to - purge_from + 1
    if total > MAX_PURGE_MESSAGES:
        PURGE.pop((bot_id(client), event.chat.id), None)
        return await event.reply_text(
            tr(
                "admin.range_covers_messages_which_over_limit_pick_closer",
                total=total,
                max_purge_messages=MAX_PURGE_MESSAGES,
            )
        )
    messages = []
    try:
        await _delete_batch(client, event.chat.id, [event.id])
        for message in range(purge_to, purge_from - 1, -1):
            messages.append(message)
            if len(messages) == 100:
                await _delete_batch(client, event.chat.id, messages)
                messages = []

        if messages:
            await _delete_batch(client, event.chat.id, messages)
        m = await client.send_message(event.chat.id, tr("admin.purged_completed"))
        await m.delete()

    except (RPCError, OSError) as e:
        LOGGER.exception("Purge failed")
        error_message = telegram_error_text(e) or tr(
            "decorators.something_went_wrong_error_has_logged"
        )
        await client.send_message(event.chat.id, error_message)
    finally:
        PURGE.pop((bot_id(client), event.chat.id), None)


@command("purge")
@anonadmin_checker
async def purge(client, event):
    chat = event.chat.id
    start = time.perf_counter()
    msgs = []
    msg = event.reply_to_message
    if not msg:
        return await reply_usage(event)
    if not await check_user(
        event, user_id=actor_id(event), privileges="can_delete_messages"
    ) and _is_group(event):
        return

    msg_id = msg.id
    to_delete = event.id - 1
    total = to_delete - msg_id + 2  # inclusive range + the command message
    if total > MAX_PURGE_MESSAGES:
        return await event.reply_text(
            tr(
                "admin.range_covers_messages_which_over_limit_reply_closer",
                total=total,
                max_purge_messages=MAX_PURGE_MESSAGES,
            )
        )

    count = 0
    await _delete_batch(client, chat, [event.id])
    for m_id in range(to_delete, msg_id - 1, -1):
        msgs.append(m_id)
        count += 1
        if len(msgs) == 100:
            await _delete_batch(client, chat, msgs)
            msgs = []

    if msgs:
        await _delete_batch(client, chat, msgs)
    time_ = time.perf_counter() - start
    m = await client.send_message(
        chat, tr("admin.purged_messages_secs", count=count, purged_messages=f"{time_:0.2f}")
    )
    await m.delete()


@command("spurge")
@anonadmin_checker
async def spurge(client, event):
    chat = event.chat.id
    msgs = []
    msg = event.reply_to_message
    if not msg:
        return await reply_usage(event)
    if not await check_user(
        event, user_id=actor_id(event), privileges="can_delete_messages"
    ) and _is_group(event):
        return

    msg_id = msg.id
    to_delete = event.id - 1
    total = to_delete - msg_id + 2
    if total > MAX_PURGE_MESSAGES:
        return await event.reply_text(
            tr(
                "admin.range_covers_messages_which_over_limit_reply_closer",
                total=total,
                max_purge_messages=MAX_PURGE_MESSAGES,
            )
        )

    await _delete_batch(client, chat, [event.id])
    for m_id in range(to_delete, msg_id - 1, -1):
        msgs.append(m_id)
        if len(msgs) == 100:
            await _delete_batch(client, chat, msgs)
            msgs = []
    if msgs:
        await _delete_batch(client, chat, msgs)


@command("del", chat_scope="group")
@anonadmin_checker
async def delete_messages(client, event):
    message = event.reply_to_message
    if not message:
        return await reply_usage(event)
    if not await check_user(event, user_id=actor_id(event), privileges="can_delete_messages"):
        return
    await client.delete_messages(event.chat.id, [message.id, event.id])


VALID_SLOWMODE_SECONDS = {0, 5, 10, 30, 60, 300, 900, 3600}


@command("slowmode", chat_scope="supergroup", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def slow_mode(client, message):
    chat_id = effective_chat_id(message)
    if not await check_user(message, user_id=actor_id(message), privileges="can_change_info"):
        return

    arg = message.command[1:]
    if not arg:
        chat = await client.get_chat(chat_id)
        current = getattr(chat, "slow_mode_delay", None) or 0
        return await message.reply_text(
            tr("admin.current_slow_mode_s", current=current)
            if current
            else tr("admin.slow_mode_currently_off")
        )

    try:
        seconds = int(arg[0])
    except ValueError:
        return await reply_usage(message)

    if seconds not in VALID_SLOWMODE_SECONDS:
        return await message.reply_text(
            tr("admin.invalid_value_valid_values")
            + ", ".join(str(v) for v in sorted(VALID_SLOWMODE_SECONDS))
        )

    await client.set_slow_mode(chat_id, seconds if seconds else None)
    if seconds:
        await message.reply_text(tr("admin.slow_mode_set_s", seconds=seconds))
    else:
        await message.reply_text(tr("admin.slow_mode_turned_off"))
    return "SLOWMODE", None, None
