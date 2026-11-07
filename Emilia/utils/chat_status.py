import asyncio

from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, PeerIdInvalid, RPCError, UserNotParticipant
from pyrogram.types import ChatAdministratorRights, ChatMember, ChatPermissions, User

from Emilia.application import LOGGER
from Emilia.locales import tr
from Emilia.utils.auth import is_dev
from Emilia.utils.cache import admin_cache
from Emilia.utils.chat_context import effective_chat_id, origin_message
from Emilia.utils.client_context import bot_id
from Emilia.utils.message_actor import actor_id, is_anonymous_admin


def _status(member: ChatMember | None) -> ChatMemberStatus | None:
    return member.status if member is not None else None


def _priv(member, name: str) -> bool:
    if member is None:
        return False
    if name == "can_be_edited":
        return bool(member.can_be_edited)
    return bool(member.privileges and getattr(member.privileges, name, False))


def _perm(member, name: str):
    if member is None:
        return None
    return getattr(member.permissions, name, None)


def member_is_admin(member) -> bool:
    return _status(member) in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR)


def member_is_present(member) -> bool:
    status = _status(member)
    if status == ChatMemberStatus.RESTRICTED:
        return bool(member.is_member)
    return status in (
        ChatMemberStatus.OWNER,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    )


def member_has_permission(member, privilege: str | None = None, *, owner=False) -> bool:
    if _status(member) == ChatMemberStatus.OWNER:
        return True
    return (
        not owner
        and _status(member) == ChatMemberStatus.ADMINISTRATOR
        and (privilege is None or _priv(member, privilege))
    )


async def get_chat_member_cached(
    client, chat_id: int, user_id: int, *, fresh=False, strict=False
) -> ChatMember | None:
    cache_key = f"chat_member:{bot_id(client)}:{chat_id}:{user_id}"
    if not fresh and not strict:
        cached = await admin_cache.get(cache_key)
        if cached is not None:
            return ChatMember(
                client=client,
                status=ChatMemberStatus[cached["status"]],
                user=User(client=client, id=user_id) if user_id > 0 else None,
                is_member=cached.get("is_member"),
                can_be_edited=cached.get("can_be_edited"),
                privileges=ChatAdministratorRights(**cached["privileges"])
                if cached.get("privileges") is not None
                else None,
                permissions=ChatPermissions(**cached["permissions"])
                if cached.get("permissions") is not None
                else None,
            )
    try:
        member = await asyncio.wait_for(
            client.get_chat_member(chat_id=chat_id, user_id=user_id), 10
        )
    except UserNotParticipant:
        await admin_cache.delete(cache_key)
        return None
    except FloodWait as error:
        if strict:
            raise
        LOGGER.warning("Member lookup rate limited in %s for %ss", chat_id, error.value)
        return None
    except PeerIdInvalid:
        if strict:
            raise
        LOGGER.debug("Member lookup peer unavailable: chat=%s user=%s", chat_id, user_id)
        return None
    except (RPCError, TimeoutError, OSError) as error:
        if strict:
            raise
        LOGGER.warning("Member lookup failed: chat=%s user=%s error=%s", chat_id, user_id, error)
        return None
    payload = {
        "status": member.status.name,
        "is_member": member.is_member,
        "can_be_edited": member.can_be_edited,
        "privileges": {
            key: value for key, value in vars(member.privileges).items() if isinstance(value, bool)
        }
        if member.privileges
        else None,
        "permissions": {
            key: value for key, value in vars(member.permissions).items() if isinstance(value, bool)
        }
        if getattr(member, "permissions", None)
        else None,
    }
    await admin_cache.set(cache_key, payload, ttl=300)
    return member


async def has_chat_permission(client, chat_id, user_id, *, owner=False, privilege=None, fresh=True):
    if not isinstance(user_id, int) or user_id <= 0 or not isinstance(chat_id, int):
        return False
    if chat_id > 0:
        return chat_id == user_id and privilege is None
    if is_dev(user_id):
        return True
    member = await get_chat_member_cached(client, chat_id, user_id, fresh=fresh)
    return member_has_permission(member, privilege, owner=owner)


async def permission_denied(event, key: str):
    text = tr(key)
    from Emilia.utils.command_policy import answer_denial

    await answer_denial(event, text, alert=True)


def _context(event, chat_id=None, user_id=None):
    message = origin_message(event)
    target = chat_id if chat_id is not None else effective_chat_id(event)
    if user_id is None:
        user_id = actor_id(event)
    client = getattr(event, "_client", None) or getattr(message, "_client", None)
    return message, client, target, user_id


async def _check_authority(
    event,
    *,
    user_id=None,
    chat_id=None,
    privileges=None,
    owner=False,
    bot=False,
    silent=False,
    fresh=True,
):
    message, client, target, actor = _context(event, chat_id, user_id)
    if client is None or target is None:
        return False
    permissions = [privileges] if isinstance(privileges, str) else list(privileges or [])
    if not bot and is_dev(actor):
        return True
    if target > 0:
        allowed = not permissions and (bot or target == actor)
        if not allowed and not silent:
            await permission_denied(event, "errors.group_only")
        return allowed
    if bot:
        actor = bot_id(client)
    # Anonymous messages establish admin status, not named rights or ownership.
    anonymous = not bot and actor == target and is_anonymous_admin(message)
    if anonymous:
        allowed = not owner and (
            not permissions or getattr(message, "_emilia_anonymous_admin_allowed", False)
        )
    elif actor is None or actor <= 0:
        allowed = False
    else:
        member = await get_chat_member_cached(client, target, actor, fresh=fresh)
        allowed = member_has_permission(member, owner=owner) and all(
            member_has_permission(member, permission, owner=owner) for permission in permissions
        )
    if not allowed and not silent:
        key = "permissions.bot_admin_required" if bot else "permissions.admin_required"
        if owner:
            key = "permissions.owner_required"
        elif permissions:
            messages = BOT_PERMISSIONS_STRINGS if bot else USERS_PERMISSIONS_STRINGS
            key = messages.get(permissions[0], key)
        await permission_denied(event, key)
    return allowed


async def is_user_admin(message, user_id=None, chat_id=None, silent=False, fresh=True):
    return await _check_authority(
        message, user_id=user_id, chat_id=chat_id, silent=silent, fresh=fresh
    )


async def is_chat_owner(message, chat_id=None, user_id=None, silent=True):
    return await _check_authority(
        message, user_id=user_id, chat_id=chat_id, owner=True, silent=silent
    )


async def is_bot_admin(message, chat_id=None, silent=False, *, fresh=True):
    return await _check_authority(message, chat_id=chat_id, bot=True, silent=silent, fresh=fresh)


async def user_has_permission(
    message, user_id=None, chat_id=None, privileges=None, silent=False, fresh=True
):
    return await _check_authority(
        message, user_id=user_id, chat_id=chat_id, privileges=privileges, silent=silent, fresh=fresh
    )


async def bot_has_permission(
    message, chat_id=None, privileges="can_change_info", silent=False, fresh=True
):
    return await _check_authority(
        message, chat_id=chat_id, privileges=privileges, bot=True, silent=silent, fresh=fresh
    )


async def check_user(
    message,
    privileges="can_change_info",
    silent=False,
    chat_id=None,
    *,
    user_id=None,
):
    return await user_has_permission(
        message, user_id=user_id, chat_id=chat_id, privileges=privileges, silent=silent
    )


async def check_bot(message, privileges="can_change_info", silent=False, chat_id=None):
    return await bot_has_permission(message, chat_id=chat_id, privileges=privileges, silent=silent)


async def check_admins(message, privileges="can_change_info", silent=False, chat_id=None):
    return await check_user(
        message, privileges=privileges, chat_id=chat_id, silent=silent
    ) and await check_bot(message, privileges=privileges, chat_id=chat_id, silent=silent)


async def can_restrict_member(message, user_id, chat_id=None):
    target = chat_id if chat_id is not None else effective_chat_id(message)
    if user_id == bot_id(message._client) or is_dev(user_id):
        return False
    member = await get_chat_member_cached(message._client, target, user_id, fresh=True, strict=True)
    return not member_is_admin(member)


BOT_PERMISSIONS_STRINGS = {
    "can_delete_messages": "chat_status.looks_like_haven_t_got_right_delete_messages",
    "can_restrict_members": "chat_status.could_not_set_telegram_chat_privileges_locks_have",
    "can_promote_members": "chat_status.don_t_have_permission_promote_demote_someone_chat",
    "can_change_info": "chat_status.don_t_have_permission_change_chat_title_photo",
    "can_pin_messages": "chat_status.don_t_have_permission_pin_messages_chat",
    "can_be_edited": "chat_status.don_t_have_enough_permission_edit_administrator_privileges",
}

USERS_PERMISSIONS_STRINGS = {
    "can_be_edited": "chat_status.don_t_have_enough_permission_edit_adminstrator_privileges",
    "can_delete_messages": "chat_status.don_t_have_enough_permission_delete_any_messages",
    "can_restrict_members": "chat_status.don_t_have_enough_permission_restrict_ban_unban",
    "can_promote_members": "chat_status.don_t_have_enough_permission_add_new_administrators",
    "can_change_info": "chat_status.don_t_have_enough_permission_change_chat_title",
    "can_invite_users": "chat_status.re_not_allowed_invite_new_users_chat",
    "can_pin_messages": "chat_status.re_not_allowed_pin_messages",
    "can_send_media_messages": "chat_status.re_not_allowed_send_audios_documents_photos_videos",
    "can_send_stickers": "chat_status.re_not_allowed_send_stickers_implies_can_send",
    "can_send_animations": "chat_status.re_not_allowed_send_animations_gifs_implies_can",
    "can_send_games": "chat_status.re_not_allowed_send_games_implies_can_send",
    "can_use_inline_bots": "chat_status.re_not_allowed_use_inline_bots_implies_can",
    "can_add_web_page_previews": "chat_status.re_not_allowed_add_web_page_previews_their",
    "can_send_polls": "chat_status.re_not_allowed_send_polls",
}
