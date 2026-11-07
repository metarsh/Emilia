import html
import re

from pyrogram import filters as pyrofilters
from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError
from pyrogram.types import LinkPreviewOptions

from Emilia.application import LOGGER, db
from Emilia.custom_filter import command, listen
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.utils.chat_status import check_user
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.errors import telegram_error_text
from Emilia.utils.message_actor import actor_id, actor_name, actor_user
from Emilia.utils.vanitas import get_user_info

vanitas_db = db.vanitas

# handlers
HLRS = re.compile("(?i)(on|off|enable|disable|yes|no)")
OFF = re.compile("(?i)(off|disable|no)")
ON = re.compile("(?i)(on|enable|yes)")


@command("antispam")
@anonadmin_checker
@log_to_channel
async def vanitas_handerl(client, van):
    args = van.matches[0].group(1)
    chat = van.chat.id
    vanitas = await vanitas_db.find_one({"chat_id": chat})
    if not args:
        return await reply_usage(van, vanitas_handerl)
    elif not re.findall(HLRS, args):
        return await reply_usage(van)
    if not await check_user(
        van, user_id=actor_id(van) if actor_user(van) else None, privileges="can_restrict_members"
    ):
        return
    elif re.findall(ON, args):
        if not vanitas:
            return await van.reply_text(tr("vanitas.vanitas_antispam_system_is_already_enabled"))
        await vanitas_db.delete_one({"chat_id": chat})
        await van.reply_text(
            tr(
                "vanitas.enabled_vanitas_antispam_system",
                chat_title=van.chat.title,
                user_name=actor_name(van),
                user_id=actor_id(van),
            )
        )
        return "ENABLED_ANTISPAM", None, None
    elif re.findall(OFF, args):
        if vanitas:
            return await van.reply_text(tr("vanitas.vanitas_antispam_system_is_already_disabled"))
        await atomic_upsert(vanitas_db, {"chat_id": chat}, {"$setOnInsert": {"chat_id": chat}})
        await van.reply_text(
            tr(
                "vanitas.disabled_vanitas_antispam_system",
                chat_title=van.chat.title,
                user_name=actor_name(van),
                user_id=actor_id(van),
            )
        )
        return "DISABLED_ANTISPAM", None, None


# ban on welcome
@listen(filters=pyrofilters.new_chat_members)
async def chk_(client, message):
    chat_id = message.chat.id
    not_vanitas = await vanitas_db.find_one({"chat_id": chat_id})
    if not_vanitas:
        return
    for new_member in message.new_chat_members:
        info = await get_user_info(new_member.id)
        if info and info["blacklisted"]:
            try:
                await client.ban_chat_member(chat_id, new_member.id)
                txt = tr(
                    "vanitas.user_has_blacklisted_vanitas_antispam_system",
                    reason=html.escape(str(info["reason"])),
                    enforcer=html.escape(str(info["enforcer"])),
                )
                txt += tr("vanitas.report_unban_at_vanitassupport")
                await message.reply_text(
                    txt,
                    parse_mode=ParseMode.HTML,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            except (RPCError, OSError) as exc:
                LOGGER.exception(
                    "Antispam action failed in chat %s for user %s", chat_id, new_member.id
                )
                await message.reply_text(telegram_error_text(exc) or tr("vanitas.action_failed"))
