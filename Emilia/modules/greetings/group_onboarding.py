import asyncio
from collections.abc import Iterable

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.errors import MessageNotModified, RPCError
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
)
from redis.exceptions import RedisError

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.custom_filter import callbackquery
from Emilia.database.common import atomic_upsert
from Emilia.database.connection import connectDB
from Emilia.database.filters import get_filters_list
from Emilia.database.locks import get_locks, lock_db, unlock_db
from Emilia.database.log_channels import get_set_channel
from Emilia.database.notes import NoteList
from Emilia.database.rules import get_private_note, get_rules
from Emilia.database.warnings import (
    get_warn_mode,
    set_warn_limit_db,
    set_warn_mode_db,
    warn_limit,
)
from Emilia.database.welcome import (
    GetWelcomemessageOnOff,
    SetCaptcha,
    SetWelcomeMessageOnOff,
    isGetCaptcha,
)
from Emilia.locales import tr
from Emilia.modules.antichannel import antichannelmode_off, antichannelmode_on
from Emilia.modules.antiflood import DB as ANTIFLOOD_DB
from Emilia.modules.antiflood import (
    _flood_status_cache as antiflood_status_cache,
)
from Emilia.modules.antiflood import _settings_cache as antiflood_settings_cache
from Emilia.modules.levels import _level_cache
from Emilia.modules.warnings.set_warn_mode import WarnModeMap
from Emilia.utils.auth import is_dev
from Emilia.utils.chat_status import (
    get_chat_member_cached,
    member_has_permission,
    member_is_admin,
    member_is_present,
)
from Emilia.utils.client_context import bot_id, bot_username
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.tasks import spawn

HIDE_LATER_SECONDS = 3600
_cleanup_tasks: dict[tuple[int, int, int], asyncio.Task] = {}

PRIVILEGE_LABELS = {
    "can_change_info": tr("group_onboarding.change_group_settings"),
    "can_delete_messages": tr("group_onboarding.delete_messages"),
    "can_restrict_members": tr("group_onboarding.restrict_members"),
    "can_pin_messages": tr("group_onboarding.pin_messages"),
    "can_invite_users": tr("group_onboarding.invite_users_variant"),
}


def _bool_text(value: bool) -> str:
    return "On" if value else "Off"


def _warn_mode_text(mode_value: int) -> str:
    mapping = {
        WarnModeMap.Ban.value: "Ban",
        WarnModeMap.Kick.value: "Kick",
        WarnModeMap.Mute.value: "Mute",
        WarnModeMap.Tban.value: tr("group_onboarding.temp_ban"),
        WarnModeMap.Tmute.value: tr("group_onboarding.temp_mute"),
    }
    return mapping.get(mode_value, "Mute")


def _format_locks(locks: Iterable[str]) -> str:
    locks = list(locks)
    if not locks:
        return "Off"
    if len(locks) <= 3:
        return ", ".join(locks)
    return f"{len(locks)} active"


async def _safe_edit(callback_query: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup):
    try:
        await callback_query.message.edit_text(
            text,
            reply_markup=reply_markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except MessageNotModified:
        pass


async def _chat_title(client: Client, chat_id: int) -> str:
    try:
        chat = await client.get_chat(chat_id)
        return chat.title or str(chat_id)
    except (RPCError, OSError):
        return str(chat_id)


async def _fetch_member(client: Client, chat_id: int, user_id: int):
    try:
        member = await get_chat_member_cached(client, chat_id, user_id, fresh=True)
        return member, None if member is not None else PermissionError("Membership unavailable")
    except RedisError as err:
        return None, err


async def _resolve_setup_access(
    client: Client,
    user_id: int,
    chat_id: int,
    required_privilege: str | None = None,
):
    chat = await client.get_chat(chat_id)
    title = chat.title or str(chat_id)
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return False, tr("errors.group_only"), title, None, None
    user_member, user_error = await _fetch_member(client, chat_id, user_id)
    if user_error is not None and not is_dev(user_id):
        return (
            False,
            (tr("group_onboarding.couldn_t_verify_admin_status_yet_can_happen", title=title)),
            title,
            None,
            None,
        )

    if not is_dev(user_id) and not member_is_admin(user_member):
        return (
            False,
            tr("group_onboarding.re_not_admin_can_t_open_setup_panel", title=title),
            title,
            user_member,
            None,
        )

    if (
        required_privilege
        and not is_dev(user_id)
        and not member_has_permission(user_member, required_privilege)
    ):
        friendly = PRIVILEGE_LABELS.get(required_privilege, required_privilege)
        return (
            False,
            tr(
                "group_onboarding.re_admin_but_step_needs_permission",
                title=title,
                friendly=friendly,
            ),
            title,
            user_member,
            None,
        )

    bot_member, _ = await _fetch_member(client, chat_id, bot_id(client))
    if not member_is_present(bot_member):
        return False, tr("channels.bot_access_required"), title, user_member, bot_member
    return True, None, title, user_member, bot_member


def _bot_permission_error(title: str, privilege: str) -> str:
    friendly = PRIVILEGE_LABELS.get(privilege, privilege)
    return tr(
        "group_onboarding.still_need_permission_before_can_do", friendly=friendly, title=title
    )


def _group_keyboard(client: Client, chat_id: int, has_rules: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                tr("group_onboarding.set_up_bot_name"),
                url=f"https://t.me/{bot_username(client)}?start=onboard_{chat_id}",
            ),
            InlineKeyboardButton(
                tr("group_onboarding.try_bot_name"),
                url=f"https://t.me/{bot_username(client)}?start=starter_{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                tr("group_onboarding.support"), url=f"https://t.me/{Config.SUPPORT_CHAT}"
            ),
            InlineKeyboardButton(
                tr("group_onboarding.news"), url=f"https://t.me/{Config.UPDATE_CHANNEL}"
            ),
        ],
    ]

    if has_rules:
        rows.append(
            [
                InlineKeyboardButton(
                    tr("filters.rules"),
                    url=f"https://t.me/{bot_username(client)}?start=rules_{chat_id}",
                    style=ButtonStyle.PRIMARY,
                ),
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                tr("group_onboarding.pin_guide"),
                callback_data="grpguide:pin",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(tr("group_onboarding.hide_in_1h"), callback_data="grpguide:hide"),
        ]
    )
    return InlineKeyboardMarkup(rows)


async def _get_settings(chat_id: int) -> dict:
    (
        welcome_on,
        captcha_on,
        rules_text,
        private_rules,
        log_channel,
        warn_limit_value,
        warn_mode_data,
        locks,
        notes,
        filters_list,
        flood_doc,
        antispam_doc,
        antichannel_doc,
        chatbot_doc,
        level_doc,
    ) = await asyncio.gather(
        GetWelcomemessageOnOff(chat_id),
        isGetCaptcha(chat_id),
        get_rules(chat_id),
        get_private_note(chat_id),
        get_set_channel(chat_id),
        warn_limit(chat_id),
        get_warn_mode(chat_id),
        get_locks(chat_id),
        NoteList(chat_id),
        get_filters_list(chat_id),
        db.antiflood_chats.find_one({"chat_id": chat_id}),
        db.vanitas.find_one({"chat_id": chat_id}),
        db.antichannel.find_one({"chat_id": chat_id}),
        db.chatbotto.find_one({"chat_id": chat_id}),
        db.onofflevel.find_one({"chat_id": chat_id}),
    )

    flood_on = bool(flood_doc and flood_doc.get("status") != "off")
    flood_limit = int((flood_doc or {}).get("limit", 10))
    rankings_on = bool(level_doc and not level_doc.get("disabled", False))

    return {
        "welcome_on": welcome_on,
        "captcha_on": captcha_on,
        "rules_set": bool(rules_text),
        "rules_private": private_rules,
        "log_channel": log_channel,
        "warn_limit": warn_limit_value,
        "warn_mode": _warn_mode_text(warn_mode_data[0]),
        "locks": list(locks),
        "notes_count": len(notes),
        "filters_count": len(filters_list),
        "flood_on": flood_on,
        "flood_limit": flood_limit,
        "antispam_on": antispam_doc is None,
        "antichannel_on": bool(antichannel_doc),
        "chatbot_on": bool(chatbot_doc),
        "rankings_on": rankings_on,
    }


async def _set_antiflood(chat_id: int, enabled: bool, limit: int | None = None):
    current = await ANTIFLOOD_DB.find_one({"chat_id": chat_id}) or {}
    if enabled:
        effective_limit = int(current.get("limit", 10) if limit is None else limit)
        await atomic_upsert(
            ANTIFLOOD_DB,
            {"chat_id": chat_id},
            {
                "$set": {
                    "chat_id": chat_id,
                    "status": "on",
                    "limit": effective_limit,
                    "action": current.get("action", "mute"),
                    "clear": current.get("clear", "yes"),
                    "timed_status": current.get("timed_status", "off"),
                    "timed_limit": int(current.get("timed_limit", 10)),
                    "timed_duration": int(current.get("timed_duration", 10)),
                    "time": current.get("time"),
                }
            },
        )
        await antiflood_status_cache.set(f"flood_on:{chat_id}", True, ttl=60)
    else:
        await atomic_upsert(ANTIFLOOD_DB, {"chat_id": chat_id}, {"$set": {"status": "off"}})
        await antiflood_status_cache.set(f"flood_on:{chat_id}", False, ttl=60)
    await antiflood_settings_cache.delete(f"antiflood_settings:{chat_id}")


async def _set_antispam(chat_id: int, enabled: bool):
    if enabled:
        await db.vanitas.delete_one({"chat_id": chat_id})
    else:
        await atomic_upsert(
            db.vanitas, {"chat_id": chat_id}, {"$setOnInsert": {"chat_id": chat_id}}
        )


async def _set_antichannel(chat_id: int, enabled: bool):
    if enabled:
        await antichannelmode_on(chat_id)
    else:
        await antichannelmode_off(chat_id)


async def _set_chatbot(chat_id: int, enabled: bool):
    if enabled:
        await atomic_upsert(db.chatbotto, {"chat_id": chat_id}, {"$set": {"chat_id": chat_id}})
    else:
        await db.chatbotto.delete_one({"chat_id": chat_id})


async def _set_rankings(chat_id: int, enabled: bool):
    if enabled:
        await atomic_upsert(
            db.onofflevel,
            {"chat_id": chat_id},
            {"$set": {"chat_id": chat_id}, "$unset": {"disabled": ""}},
        )
    else:
        await atomic_upsert(
            db.onofflevel, {"chat_id": chat_id}, {"$set": {"chat_id": chat_id, "disabled": True}}
        )
    await _level_cache.delete(f"lvl:{chat_id}")


async def _set_lock_bundle(chat_id: int, bundle: str):
    if bundle == "basic":
        targets = {"invitelink", "forward"}
    else:
        targets = {"invitelink", "forward", "url", "inline"}

    managed = {"invitelink", "forward", "url", "inline"}
    for lock_name in targets:
        await lock_db(chat_id, lock_name)
    for lock_name in managed - targets:
        await unlock_db(chat_id, lock_name)


async def _apply_preset(chat_id: int, preset: str):
    await SetWelcomeMessageOnOff(chat_id, True)
    await set_warn_mode_db(chat_id, WarnModeMap.Mute.value)

    if preset == "strict":
        await SetCaptcha(chat_id, True)
        await _set_antiflood(chat_id, True, limit=10)
        await set_warn_limit_db(chat_id, 3)
        await _set_lock_bundle(chat_id, "basic")
        await _set_antispam(chat_id, True)
        await _set_antichannel(chat_id, False)
        await _set_chatbot(chat_id, False)
        await _set_rankings(chat_id, False)
        return tr("group_onboarding.applied_strict_community")

    if preset == "chill":
        await SetCaptcha(chat_id, False)
        await _set_antiflood(chat_id, True, limit=15)
        await set_warn_limit_db(chat_id, 4)
        await _set_antichannel(chat_id, False)
        await _set_chatbot(chat_id, False)
        await _set_rankings(chat_id, False)
        return tr("group_onboarding.applied_chill_group")

    if preset == "media":
        await SetCaptcha(chat_id, False)
        await _set_antiflood(chat_id, True, limit=12)
        await set_warn_limit_db(chat_id, 4)
        await _set_lock_bundle(chat_id, "basic")
        await _set_antispam(chat_id, True)
        await _set_antichannel(chat_id, True)
        await _set_chatbot(chat_id, False)
        await _set_rankings(chat_id, False)
        return tr("group_onboarding.applied_media_anime_group")

    await SetCaptcha(chat_id, False)
    await _set_antiflood(chat_id, True, limit=18)
    await set_warn_limit_db(chat_id, 5)
    await _set_antispam(chat_id, True)
    await _set_antichannel(chat_id, False)
    await _set_chatbot(chat_id, True)
    await _set_rankings(chat_id, True)
    return tr("group_onboarding.applied_fun_group")


def _toggle_label(prefix: str, enabled: bool) -> str:
    return f"{prefix} Off" if enabled else f"{prefix} On"


def _toggle_state(enabled: bool) -> str:
    return "off" if enabled else "on"


def _setup_home_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("group_onboarding.permissions_check"),
                    callback_data=f"onbpm:permissions:{chat_id}",
                ),
                InlineKeyboardButton(
                    tr("group_onboarding.choose_preset"),
                    callback_data=f"onbpm:presets:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.welcome_rules"),
                    callback_data=f"onbpm:welcome:{chat_id}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    tr("group_onboarding.protection"),
                    callback_data=f"onbpm:protection:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.log_channel"),
                    callback_data=f"onbpm:logs:{chat_id}",
                ),
                InlineKeyboardButton(
                    tr("group_onboarding.optional_extras"),
                    callback_data=f"onbpm:extras:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.summary"),
                    callback_data=f"onbpm:summary:{chat_id}",
                )
            ],
        ]
    )


async def _render_setup_home(client: Client, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    text = tr(
        "group_onboarding.emilia_setup_connected_ll_keep_short_recommended_order", title=title
    )
    return text, _setup_home_keyboard(chat_id)


def _permission_lines(member, items: Iterable[tuple[str, str]]) -> str:
    return "\n".join(
        f"- {label}: {'Yes' if member_has_permission(member, privilege) else 'No'}"
        for label, privilege in items
    )


async def _render_permissions(
    client: Client, chat_id: int, user_id: int
) -> tuple[str, InlineKeyboardMarkup]:
    _, _, title, user_member, bot_member = await _resolve_setup_access(client, user_id, chat_id)

    permission_items = [
        (tr("group_onboarding.delete_messages_render_permissions"), "can_delete_messages"),
        (tr("group_onboarding.restrict_members_render_permissions"), "can_restrict_members"),
        (tr("group_onboarding.pin_messages_render_permissions"), "can_pin_messages"),
        (tr("group_onboarding.invite_users"), "can_invite_users"),
    ]

    bot_status = (
        tr("group_onboarding.am_not_admin_there_yet")
        if not member_is_admin(bot_member)
        else _permission_lines(bot_member, permission_items)
    )
    your_status = (
        tr("group_onboarding.verified_admin")
        if member_is_admin(user_member)
        else tr("group_onboarding.current_admin_state_will_checked_again_button_presses")
    )

    text = tr(
        "group_onboarding.setup_1_6_permissions_check_chat_these_main",
        title=title,
        your_status=your_status,
        bot_status=bot_status,
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("group_onboarding.refresh"),
                    callback_data=f"onbpm:permissions:{chat_id}",
                ),
                InlineKeyboardButton(
                    tr("group_onboarding.choose_preset"),
                    callback_data=f"onbpm:presets:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.back_to_setup"),
                    callback_data=f"onbpm:home:{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )
    return text, keyboard


async def _render_presets(client: Client, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    text = tr("group_onboarding.setup_2_6_choose_preset_pick_closest_starting", title=title)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("group_onboarding.strict_community"),
                    callback_data=f"onbpm:applypreset:strict:{chat_id}",
                ),
                InlineKeyboardButton(
                    tr("group_onboarding.chill_group"),
                    callback_data=f"onbpm:applypreset:chill:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.media_anime_group"),
                    callback_data=f"onbpm:applypreset:media:{chat_id}",
                ),
                InlineKeyboardButton(
                    tr("group_onboarding.fun_group"),
                    callback_data=f"onbpm:applypreset:fun:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.back_to_setup"),
                    callback_data=f"onbpm:home:{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )
    return text, keyboard


async def _render_welcome_rules(client: Client, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    rows = [
        [
            InlineKeyboardButton(
                _toggle_label("Welcome", settings["welcome_on"]),
                callback_data=f"onbpm:setwelcome:{_toggle_state(settings['welcome_on'])}:{chat_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                _toggle_label("Captcha", settings["captcha_on"]),
                callback_data=f"onbpm:setcaptcha:{_toggle_state(settings['captcha_on'])}:{chat_id}",
            ),
        ],
    ]

    if settings["rules_set"]:
        rows.append(
            [
                InlineKeyboardButton(
                    tr("group_onboarding.open_rules"),
                    url=f"https://t.me/{bot_username(client)}?start=rules_{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                tr("group_onboarding.back_to_setup"),
                callback_data=f"onbpm:home:{chat_id}",
                style=ButtonStyle.PRIMARY,
            )
        ]
    )

    text = tr(
        "group_onboarding.setup_3_6_welcome_rules_captcha_chat_welcome",
        title=title,
        welcome_on=_bool_text(settings["welcome_on"]),
        rules="Set" if settings["rules_set"] else "Not Set",
        captcha_on=_bool_text(settings["captcha_on"]),
    )
    return text, InlineKeyboardMarkup(rows)


async def _render_protection(client: Client, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    text = (
        tr(
            "group_onboarding.setup_4_6_protection_chat_antiflood",
            title=title,
            flood_on=_bool_text(settings["flood_on"]),
        )
        + (f" ({settings['flood_limit']} msgs)" if settings["flood_on"] else "")
        + tr(
            "group_onboarding.warn_limit_warn_mode_locks_anti_spam_anti",
            warn_limit=settings["warn_limit"],
            warn_mode=settings["warn_mode"],
            locks=_format_locks(settings["locks"]),
            antispam_on=_bool_text(settings["antispam_on"]),
            antichannel_on=_bool_text(settings["antichannel_on"]),
        )
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _toggle_label("Antiflood", settings["flood_on"]),
                    callback_data=f"onbpm:setaf:{_toggle_state(settings['flood_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.warn_limit_3"),
                    callback_data=f"onbpm:setwarn:3:{chat_id}",
                ),
                InlineKeyboardButton(
                    tr("group_onboarding.warn_limit_5"),
                    callback_data=f"onbpm:setwarn:5:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.basic_locks"),
                    callback_data=f"onbpm:setlocks:basic:{chat_id}",
                ),
                InlineKeyboardButton(
                    tr("group_onboarding.strict_locks"),
                    callback_data=f"onbpm:setlocks:strict:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    _toggle_label("Anti-Spam", settings["antispam_on"]),
                    callback_data=f"onbpm:setspam:{_toggle_state(settings['antispam_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    _toggle_label("Anti-Channel", settings["antichannel_on"]),
                    callback_data=f"onbpm:setchannel:{_toggle_state(settings['antichannel_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.back_to_setup"),
                    callback_data=f"onbpm:home:{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )
    return text, keyboard


async def _render_logs(client: Client, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    text = tr(
        "group_onboarding.setup_5_6_log_channel_chat_current_log",
        title=title,
        log_channel=settings["log_channel"] or "Not Set",
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("group_onboarding.refresh"),
                    callback_data=f"onbpm:logs:{chat_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.back_to_setup"),
                    callback_data=f"onbpm:home:{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )
    return text, keyboard


async def _render_extras(client: Client, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    text = tr(
        "group_onboarding.setup_6_6_optional_extras_chat_chatbot_rankings",
        title=title,
        chatbot_on=_bool_text(settings["chatbot_on"]),
        rankings_on=_bool_text(settings["rankings_on"]),
        notes_count=settings["notes_count"],
        filters_count=settings["filters_count"],
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    _toggle_label("Chatbot", settings["chatbot_on"]),
                    callback_data=f"onbpm:setchatbot:{_toggle_state(settings['chatbot_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    _toggle_label("Rankings", settings["rankings_on"]),
                    callback_data=f"onbpm:setrank:{_toggle_state(settings['rankings_on'])}:{chat_id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("group_onboarding.back_to_setup"),
                    callback_data=f"onbpm:home:{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )
    return text, keyboard


async def _render_summary(client: Client, chat_id: int) -> tuple[str, InlineKeyboardMarkup]:
    title = await _chat_title(client, chat_id)
    settings = await _get_settings(chat_id)
    text = tr(
        "group_onboarding.setup_summary_chat_welcome_rules_captcha_antiflood_warn",
        title=title,
        welcome_on=_bool_text(settings["welcome_on"]),
        rules="Set" if settings["rules_set"] else "Not Set",
        captcha_on=_bool_text(settings["captcha_on"]),
        flood_on=_bool_text(settings["flood_on"]),
        warn_limit=settings["warn_limit"],
        locks=_format_locks(settings["locks"]),
        log_channel=settings["log_channel"] or "Not Set",
        chatbot_on=_bool_text(settings["chatbot_on"]),
        rankings_on=_bool_text(settings["rankings_on"]),
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("group_onboarding.back_to_setup"),
                    callback_data=f"onbpm:home:{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )
    return text, keyboard


async def _render_setup_screen(client: Client, chat_id: int, screen: str, user_id: int):
    if screen == "permissions":
        return await _render_permissions(client, chat_id, user_id)
    if screen == "presets":
        return await _render_presets(client, chat_id)
    if screen == "welcome":
        return await _render_welcome_rules(client, chat_id)
    if screen == "protection":
        return await _render_protection(client, chat_id)
    if screen == "logs":
        return await _render_logs(client, chat_id)
    if screen == "extras":
        return await _render_extras(client, chat_id)
    if screen == "summary":
        return await _render_summary(client, chat_id)
    return await _render_setup_home(client, chat_id)


async def _render_starter_home(client: Client, chat_id: int):
    title = await _chat_title(client, chat_id)
    rules_text = await get_rules(chat_id)
    text = tr("group_onboarding.emilia_starter_guide_don_t_need_full_help", title=title)
    rows = [
        [
            InlineKeyboardButton(tr("help.fun"), callback_data=f"starterpm:fun:{chat_id}"),
            InlineKeyboardButton(tr("help.anime"), callback_data=f"starterpm:anime:{chat_id}"),
        ],
        [
            InlineKeyboardButton(
                tr("group_onboarding.utilities"),
                callback_data=f"starterpm:utilities:{chat_id}",
            ),
            InlineKeyboardButton(
                tr("group_onboarding.chat_with_bot_name"),
                callback_data=f"starterpm:chat:{chat_id}",
            ),
        ],
    ]
    if rules_text:
        rows.append(
            [
                InlineKeyboardButton(
                    tr("filters.rules"),
                    url=f"https://t.me/{bot_username(client)}?start=rules_{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        )
    return text, InlineKeyboardMarkup(rows)


def _starter_back(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("buttons.back"),
                    callback_data=f"starterpm:home:{chat_id}",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        ]
    )


async def _render_starter_fun(chat_id: int):
    text = tr("group_onboarding.fun_try_these_joke_gif_cat_truth_dare")
    return text, _starter_back(chat_id)


async def _render_starter_anime(chat_id: int):
    text = tr("group_onboarding.anime_try_these_anime_frieren_quote_browse_watch")
    return text, _starter_back(chat_id)


async def _render_starter_utilities(chat_id: int):
    text = tr("group_onboarding.utilities_try_these_id_wiki_emilia_github_torvalds")
    return text, _starter_back(chat_id)


async def _render_starter_chat(chat_id: int):
    enabled = bool(await db.chatbotto.find_one({"chat_id": chat_id}))
    if enabled:
        text = tr("group_onboarding.chat_emilia_reply_one_messages_will_reply_back")
    else:
        text = tr("group_onboarding.chat_emilia_reply_one_messages_after_admins_enable")
    return text, _starter_back(chat_id)


async def _render_starter_screen(client: Client, chat_id: int, screen: str):
    if screen == "fun":
        return await _render_starter_fun(chat_id)
    if screen == "anime":
        return await _render_starter_anime(chat_id)
    if screen == "utilities":
        return await _render_starter_utilities(chat_id)
    if screen == "chat":
        return await _render_starter_chat(chat_id)
    return await _render_starter_home(client, chat_id)


async def _delete_later(client: Client, chat_id: int, message_id: int, delay: int):
    key = (bot_id(client), chat_id, message_id)
    try:
        await asyncio.sleep(delay)
        await client.delete_messages(chat_id, message_id)
    except (RPCError, OSError):
        LOGGER.debug("Could not delete the onboarding message", exc_info=True)
    finally:
        if _cleanup_tasks.get(key) is asyncio.current_task():
            _cleanup_tasks.pop(key, None)


async def send_group_onboarding(client: Client, chat_id: int):
    has_rules = bool(await get_rules(chat_id))
    text = tr("group_onboarding.hi_m_thanks_adding_ll_keep_short_can", bot_name=Config.BOT_NAME)
    return await client.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=_group_keyboard(client, chat_id, has_rules),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def onboarding_redirect(client: Client, message, chat_id: int):
    ok, reason, title, _, _ = await _resolve_setup_access(client, message.from_user.id, chat_id)
    if not ok:
        await message.reply_text(reason, link_preview_options=LinkPreviewOptions(is_disabled=True))
        return

    await connectDB(message.from_user.id, chat_id)
    text, keyboard = await _render_setup_home(client, chat_id)
    await message.reply_text(
        text,
        reply_markup=keyboard,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


async def starter_redirect(client: Client, message, chat_id: int):
    text, keyboard = await _render_starter_home(client, chat_id)
    await message.reply_text(
        text,
        reply_markup=keyboard,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@callbackquery(filters=filters.regex("^grpguide:"), access=CallbackAccess(public=True))
async def group_guide_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.message.chat.type == ChatType.PRIVATE:
        return

    action = (callback_query.data or "").split(":")[1]
    ok, reason, title, _, bot_member = await _resolve_setup_access(
        client,
        callback_query.from_user.id,
        callback_query.message.chat.id,
        required_privilege="can_pin_messages" if action == "pin" else None,
    )
    if not ok:
        await callback_query.answer(reason, show_alert=True)
        return

    chat_id = callback_query.message.chat.id
    if action == "pin":
        if not member_has_permission(bot_member, "can_pin_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_pin_messages"), show_alert=True
            )
            return
        try:
            await client.pin_chat_message(
                chat_id,
                callback_query.message.id,
                disable_notification=True,
            )
            await callback_query.answer(tr("group_onboarding.guide_pinned"))
        except (RPCError, OSError):
            await callback_query.answer(
                tr("group_onboarding.i_couldn_t_pin_the_guide_just"),
                show_alert=True,
            )
        return

    key = (bot_id(client), chat_id, callback_query.message.id)
    old_task = _cleanup_tasks.get(key)
    if old_task and not old_task.done():
        old_task.cancel()
    _cleanup_tasks[key] = spawn(
        _delete_later(client, chat_id, callback_query.message.id, HIDE_LATER_SECONDS),
        name="onboarding_hide",
    )
    await callback_query.answer(tr("group_onboarding.i_will_hide_this_guide_in_1"))


@callbackquery(filters=filters.regex("^onbpm:"), access=CallbackAccess(public=True))
async def onboarding_pm_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.message.chat.type != ChatType.PRIVATE:
        return

    data = (callback_query.data or "").split(":")
    if len(data) < 3:
        return

    action = data[1]
    chat_id = int(data[-1])
    user_id = callback_query.from_user.id

    privilege = None
    if action in {"setwelcome", "setwarn", "setlocks", "setchatbot", "setrank"}:
        privilege = "can_change_info"
    elif action in {"setcaptcha", "setaf", "setspam", "setchannel", "applypreset"}:
        privilege = "can_restrict_members"

    ok, reason, title, _, bot_member = await _resolve_setup_access(
        client, user_id, chat_id, required_privilege=privilege
    )
    if not ok:
        await callback_query.answer(reason, show_alert=True)
        return

    if action == "applypreset":
        if not member_has_permission(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        if not member_has_permission(bot_member, "can_delete_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_delete_messages"), show_alert=True
            )
            return
        preset = data[2]
        result = await _apply_preset(chat_id, preset)
        await callback_query.answer(result)
        text, keyboard = await _render_welcome_rules(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setwelcome":
        enabled = data[2] == "on"
        await SetWelcomeMessageOnOff(chat_id, enabled)
        await callback_query.answer(tr("group_onboarding.welcome", enabled=_bool_text(enabled)))
        text, keyboard = await _render_welcome_rules(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setcaptcha":
        if not member_has_permission(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        enabled = data[2] == "on"
        await SetCaptcha(chat_id, enabled)
        await callback_query.answer(tr("group_onboarding.captcha", enabled=_bool_text(enabled)))
        text, keyboard = await _render_welcome_rules(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setaf":
        if not member_has_permission(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        if not member_has_permission(bot_member, "can_delete_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_delete_messages"), show_alert=True
            )
            return
        enabled = data[2] == "on"
        await _set_antiflood(chat_id, enabled)
        await callback_query.answer(tr("group_onboarding.antiflood", enabled=_bool_text(enabled)))
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setwarn":
        limit_value = int(data[2])
        await set_warn_limit_db(chat_id, limit_value)
        await callback_query.answer(tr("group_onboarding.warn_limit_set", limit_value=limit_value))
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setlocks":
        if not member_has_permission(bot_member, "can_delete_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_delete_messages"), show_alert=True
            )
            return
        bundle = data[2]
        await _set_lock_bundle(chat_id, bundle)
        await callback_query.answer(
            tr("group_onboarding.basic_locks_applied")
            if bundle == "basic"
            else tr("group_onboarding.strict_locks_applied")
        )
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setspam":
        if not member_has_permission(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        enabled = data[2] == "on"
        await _set_antispam(chat_id, enabled)
        await callback_query.answer(tr("group_onboarding.anti_spam", enabled=_bool_text(enabled)))
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setchannel":
        if not member_has_permission(bot_member, "can_restrict_members"):
            await callback_query.answer(
                _bot_permission_error(title, "can_restrict_members"), show_alert=True
            )
            return
        if not member_has_permission(bot_member, "can_delete_messages"):
            await callback_query.answer(
                _bot_permission_error(title, "can_delete_messages"), show_alert=True
            )
            return
        enabled = data[2] == "on"
        await _set_antichannel(chat_id, enabled)
        await callback_query.answer(
            tr("group_onboarding.anti_channel", enabled=_bool_text(enabled))
        )
        text, keyboard = await _render_protection(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setchatbot":
        enabled = data[2] == "on"
        await _set_chatbot(chat_id, enabled)
        await callback_query.answer(tr("group_onboarding.chatbot", enabled=_bool_text(enabled)))
        text, keyboard = await _render_extras(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    if action == "setrank":
        enabled = data[2] == "on"
        await _set_rankings(chat_id, enabled)
        await callback_query.answer(tr("group_onboarding.rankings", enabled=_bool_text(enabled)))
        text, keyboard = await _render_extras(client, chat_id)
        await _safe_edit(callback_query, text, keyboard)
        return

    await callback_query.answer()
    text, keyboard = await _render_setup_screen(client, chat_id, action, user_id)
    await _safe_edit(callback_query, text, keyboard)


@callbackquery(filters=filters.regex("^starterpm:"), access=CallbackAccess(public=True))
async def starter_pm_callback(client: Client, callback_query: CallbackQuery):
    if callback_query.message.chat.type != ChatType.PRIVATE:
        return

    data = (callback_query.data or "").split(":")
    if len(data) < 3:
        return

    action = data[1]
    chat_id = int(data[2])

    await callback_query.answer()
    text, keyboard = await _render_starter_screen(client, chat_id, action)
    await _safe_edit(callback_query, text, keyboard)
