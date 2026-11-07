from pymongo.errors import PyMongoError
from pyrogram import enums, filters
from pyrogram.enums import ButtonStyle
from pyrogram.errors import BadRequest, RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, User
from redis.exceptions import RedisError

from Emilia.application import LOGGER, db
from Emilia.custom_filter import callbackquery, command
from Emilia.database.afk import is_afk
from Emilia.database.karma import user_global_karma
from Emilia.database.user_info import get_bio, get_me, set_bio, set_me
from Emilia.locales import tr
from Emilia.utils.auth import is_dev, is_owner
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.get_user import normalize_peer, reply_target, resolve_target
from Emilia.utils.menu_guard import remember_menu
from Emilia.utils.message_actor import actor_id
from Emilia.utils.vanitas import get_user_info

chatlevels = db.chatlevels

btn = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                tr("buttons.close"),
                callback_data="close_info",
                style=ButtonStyle.DANGER,
            )
        ]
    ]
)


@callbackquery(filters=filters.regex(pattern="close_info"))
async def close_info(_, cb):
    await cb.answer()
    await cb.message.delete()


@command("info", disable=True, allow_connected=True)
@anonadmin_checker(named=True)
async def _info(_, message):
    chat_id = effective_chat_id(message)
    user, _reason = await resolve_target(message, default_to_sender=True)
    if user is None:
        return await message.reply_text(tr("errors.user_not_found"))
    user_id = user.id

    text = tr("bio.info_found")
    text += tr("bio.user_id", user_id=user_id)
    text += tr("bio.first_name", user_name=user.first_name)
    if user.last_name:
        text += tr("bio.last_name", last_name=user.last_name)
    if user.username:
        text += f"**Username**: @{user.username}\n"
    text += f"**Link**: {user.mention}\n"
    try:
        karma = await user_global_karma(user_id)
        text += tr("bio.global_karma_points", karma=karma)
    except PyMongoError:
        LOGGER.debug("Optional karma lookup failed", exc_info=True)

    text += tr("bio.premium_user", premium_user="Yes" if user.is_premium else "No")
    if (await _.get_chat(chat_id)).type in (enums.ChatType.GROUP, enums.ChatType.SUPERGROUP):
        text += "\n**Presence**: "
        member = None
        try:
            member = await _.get_chat_member(chat_id, user_id)
            status_map = {
                enums.ChatMemberStatus.OWNER: "Owner",
                enums.ChatMemberStatus.ADMINISTRATOR: "Administrator",
                enums.ChatMemberStatus.MEMBER: "Member",
                enums.ChatMemberStatus.LEFT: "Left",
                enums.ChatMemberStatus.BANNED: "Banned",
                enums.ChatMemberStatus.RESTRICTED: "Restricted",
            }
            status_str = status_map.get(member.status, "Unknown")
            text += f"{status_str}\n"

            if member.custom_title:
                text += tr("bio.user_holds_title_here", custom_title=member.custom_title)

        except BadRequest:
            text += tr("bio.not_chat")

        # AFK Check
        if await is_afk(user_id):
            text += tr("bio.status_afk")

    if is_owner(user_id):
        text += tr("bio.he_cute_neko_arsshhhhhhhhhh_3")
    elif is_dev(user_id):
        text += tr("bio.one_developers_respect")

    try:
        info = await get_user_info(user_id)
        if info and info["blacklisted"]:
            text += tr("bio.safety_status")
            text += tr("bio.spamwatch_banned")
            text += f"Reason: {info['reason']}\n"
    except RedisError:
        LOGGER.debug("Optional antispam lookup failed", exc_info=True)

    # Chat Levels Info (Prestige & Rep)
    try:
        level_doc = await chatlevels.find_one({"user_id": user_id, "chat_id": chat_id})
        if level_doc:
            prestige = level_doc.get("prestige", 0)
            rep = level_doc.get("reputation", 0)
            current_xp = level_doc.get("points", 0)

            if prestige > 0 or rep > 0 or current_xp > 0:
                text += tr("bio.activity_stats")
                if prestige > 0:
                    text += tr("bio.prestige_level", prestige=prestige)
                if rep > 0:
                    text += f"**Reputation**: {rep}\n"
                text += f"**XP**: {current_xp}\n"
    except PyMongoError:
        LOGGER.debug("Optional level lookup failed", exc_info=True)

    # Media Dispatch
    # download_media is IO heavy.
    if user.photo:
        pic = None
        try:
            pic = await _.download_media(user.photo.big_file_id, in_memory=True)
            sent = await _.send_photo(message.chat.id, photo=pic, caption=text, reply_markup=btn)
        except (RPCError, OSError, TimeoutError):
            LOGGER.debug("Profile photo delivery failed", exc_info=True)
            sent = await message.reply(text, reply_markup=btn)
        finally:
            if pic is not None:
                pic.close()
    else:
        sent = await message.reply(text, reply_markup=btn)
    await remember_menu(sent, actor_id(message), client=_)


@command("ginfo", disable=True)
@anonadmin_checker(named=True)
async def _ginfo(_, message):
    if len(message.text.split()) < 2:
        await reply_usage(message, _ginfo)
        return
    arg = message.text.split()[1]
    chat_id = normalize_peer(arg)
    try:
        chat = await _.get_chat(chat_id)
        administrators = []
        async for m in _.get_chat_members(chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS):
            administrators.append(m)
    except RPCError:
        return await message.reply_text(tr("bio.chat_id_or_username_is_invalid_or"))
    text = f"**ID**: `{chat.id}`\n\n"
    text += f"**Title**: `{chat.title}`\n"
    text += tr("bio.chat_type", type=chat.type.value)
    text += tr("bio.dc_id", dc_id=chat.dc_id)
    text += f"**Restricted**: `{chat.is_restricted}`\n"
    text += f"**Scam**: `{chat.is_scam}`\n"
    if chat.username:
        text += f"**Username**: @{chat.username}\n\n"
    text += tr("bio.member_stats")
    text += f"**Admins**: `{len(administrators)}`\n"
    text += f"**Users**: `{chat.members_count}`\n\n"
    text += tr("bio.admin_list")
    for i in administrators:
        if i.user.is_bot or i.user.is_deleted:
            pass
        text += f"\n• {i.user.mention}"
    sent = await message.reply_text(text, reply_markup=btn)
    await remember_menu(sent, actor_id(message), client=_)


@command("gifid", disable=True)
async def _ginfo0(_, message):
    replied = message.reply_to_message
    if replied and replied.animation:
        return await message.reply_text(tr("bio.gif_id", file_id=replied.animation.file_id))
    await reply_usage(message, _ginfo0)
    return


@command("setme", disable=True, chat_scope="group")
async def setme(_, message):
    user = reply_target(message, default_to_sender=True)
    if not isinstance(user, User):
        return await message.reply_text(tr("errors.user_not_found"))
    user_id = user.id
    if user_id in [777000, 1087968824]:
        return await message.reply_text(tr("bio.some_error_occured"))
    try:
        info = message.text.split(None, 1)[1]
    except IndexError:
        return await reply_usage(message)
    if len(info) > 70:
        return await message.reply_text(
            tr("bio.info_needs_under_70_characters_have", info=len(info))
        )
    await set_me(user_id, info)
    return await message.reply_text(tr("bio.information_updated"))


@command("me", disable=True)
async def show_me(_, message):
    user, _reason = await resolve_target(message, default_to_sender=True)
    if user is None:
        return await message.reply_text(tr("errors.user_not_found"))
    user_id = user.id
    mention = user.mention
    info = await get_me(user_id)
    if not info:
        return await message.reply_text(
            tr("bio.hasn_t_set_info_message_about_themself_yet", user_mention=mention)
        )
    return await message.reply_text(
        tr("bio.show_user_mention_info", user_mention=mention, info=info)
    )


@command("setbio", disable=True, chat_scope="group")
async def setbio(_, message):
    user = reply_target(message, default_to_sender=True)
    if not isinstance(user, User):
        return await message.reply_text(tr("errors.user_not_found"))
    user_id = user.id
    if user_id in [777000, 1087968824]:
        return await message.reply_text(tr("bio.some_error_occured"))
    try:
        bio = message.text.split(None, 1)[1]
    except IndexError:
        return await reply_usage(message)
    if len(bio) > 70:
        return await message.reply_text(tr("bio.the_info_needs_to_be_under_70", bio=len(bio)))
    await set_bio(user_id, bio)
    return await message.reply_text(tr("bio.information_updated"))


@command("bio", disable=True)
async def show_bio(_, message):
    user, _reason = await resolve_target(message, default_to_sender=True)
    if user is None:
        return await message.reply_text(tr("errors.user_not_found"))
    user_id = user.id
    mention = user.mention
    bio = await get_bio(user_id)
    if not bio:
        return await message.reply_text(
            tr("bio.hasn_t_set_info_message_about_themself_yet", user_mention=mention)
        )
    return await message.reply_text(
        tr("bio.show_user_mention_info", user_mention=mention, info=bio)
    )
