import asyncio
import csv
import html
import os
import uuid
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from xml.etree.ElementTree import Element, tostring

import orjson
from pyrogram.enums import ButtonStyle, ChatType, ParseMode
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import callbackquery as inline
from Emilia.custom_filter import command, listen
from Emilia.database import federations as db
from Emilia.locales import tr
from Emilia.utils.admins import get_user_reason as get_user
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import (
    bot_has_permission,
    check_user,
    is_chat_owner,
    is_user_admin,
)
from Emilia.utils.client_context import bot_id
from Emilia.utils.command_help import reply_usage
from Emilia.utils.confirmation import read_confirmation, send_confirmation
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.message_actor import actor_id, actor_user
from Emilia.utils.tg_safe import flood_safe

# im_bannable
ADMINS = list(Config.DEV_USERS) + [Config.BOT_ID, Config.OWNER_ID]
MAX_IMPORT_BYTES = 5 * 1024**2
MAX_IMPORT_ROWS = 10_000


def _read_import(content, mode):
    if mode == "csv":
        rows = csv.DictReader(StringIO(content.decode("utf-8-sig")), strict=True)
        fields = ("User ID", "Name", "Reason")
        headers = rows.fieldnames or []
        if not set(fields).issubset(headers) or len(headers) != len(set(headers)):
            raise ValueError("Federation import has invalid CSV headers")
    elif mode == "json":
        rows = (orjson.loads(line) for line in content.splitlines() if line.strip())
        fields = ("user_id", "name", "reason")
    else:
        raise ValueError("Unsupported federation import format")
    result = []
    for row in rows:
        if len(result) >= MAX_IMPORT_ROWS:
            raise ValueError("Federation import contains too many rows")
        if not isinstance(row, dict):
            raise ValueError("Federation import rows must be objects")
        if None in row:
            raise ValueError("Federation import row has extra CSV values")
        try:
            user_id, name, reason = (row[field] for field in fields)
        except KeyError as exc:
            raise ValueError("Federation import is missing a field") from exc
        if isinstance(user_id, str):
            if not user_id.isascii() or not user_id.isdecimal() or len(user_id) > 19:
                raise ValueError("Invalid federation user ID")
            user_id = int(user_id)
        if isinstance(user_id, bool) or not isinstance(user_id, int) or not 0 < user_id < 2**63:
            raise ValueError("Invalid federation user ID")
        if not isinstance(name, str) or not isinstance(reason, str):
            raise ValueError("Federation names and reasons must be strings")
        result.append({"user_id": user_id, "name": name, "reason": reason})
    return result


async def _fed_confirmation(client, query, action, *, role=None):
    data = await read_confirmation(client, query, action)
    if data is None:
        return None
    fed = await db.search_fed_by_id(data["fed_id"])
    if not fed or fed.get("owner_id") != data["owner_id"]:
        await query.answer(tr("federations.this_federation_no_longer_exists"), show_alert=True)
        return None
    if role and query.from_user.id != data[role]:
        await query.answer(tr("federations.this_action_is_not_intended_for_you"), show_alert=True)
        return None
    if await read_confirmation(client, query, action, consume=True) is None:
        return None
    return data, fed


async def is_user_fed_admin(fed_id, user_id):
    fed_admins = await db.get_all_fed_admins(fed_id) or []
    if int(user_id) in fed_admins or int(user_id) == Config.OWNER_ID:
        return True
    else:
        return False


@command("newfed", chat_scope="private")
async def newfed(client, message):

    if len(message.text.split(" ", 1)) == 2:
        name = message.text.split(" ", 1)[1]
    else:
        return await message.reply_text(tr("federations.you_need_to_give_your_federation_a"))

    f_owner = await db.get_user_owner_fed_full(actor_user(message).id)
    if f_owner:
        fed_name = f_owner[1]
        return await message.reply_text(
            tr("federations.already_have_federation_called_can_t_create_another", fed_name=fed_name)
        )
    if len(name) > 64:
        return await message.reply_text(tr("federations.federation_names_can_only_be_upto_64"))
    fed_id = str(uuid.uuid4())
    if not await db.new_fed(actor_user(message).id, fed_id, name):
        return await message.reply_text(tr("federations.creation_busy"))
    await message.reply_text(
        tr(
            "federations.created_new_federation_fedid_use_id_join_federation",
            fed_id=fed_id,
            fed_id_2=fed_id,
        )
    )


@command("delfed", chat_scope="private")
async def del_fed(client, message):
    fedowner = await db.get_user_owner_fed_full(actor_user(message).id)
    if not fedowner:
        return await message.reply_text(tr("federations.it_doesn_t_look_like_you_have"))
    name = fedowner[1]
    fed_id = fedowner[0]
    await send_confirmation(
        message,
        tr("federations.are_you_sure_you_want_to_delete", name=html.escape(name)),
        "fed_delete",
        {"fed_id": fed_id, "owner_id": actor_user(message).id},
        [
            ("rmfed", tr("federations.delete_federation"), ButtonStyle.DANGER),
            ("cancelrmfed", tr("buttons.cancel"), ButtonStyle.DEFAULT),
        ],
        client=client,
        users=[actor_user(message).id],
    )


@inline(pattern=r"rmfed(\_(.*))")
async def delete_federation_callback(client, query):
    result = await _fed_confirmation(client, query, "fed_delete", role="owner_id")
    if result is None:
        return
    data, _ = result
    if not await db.del_fed(data["fed_id"], query.from_user.id):
        return await query.answer(
            tr("federations.this_federation_no_longer_exists"), show_alert=True
        )
    await query.edit_message_text(tr("federations.you_have_deleted_your_federation_all_chats"))


@inline(pattern=r"^cancelrmfed_")
async def cancel_federation_delete(client, query):
    if await _fed_confirmation(client, query, "fed_delete", role="owner_id") is None:
        return
    await query.edit_message_text(tr("federations.federation_deletion_cancelled"))


@command("renamefed", chat_scope="private")
async def rename(client, message):
    fedowner = await db.get_user_owner_fed_full(actor_user(message).id)
    if not fedowner:
        return await message.reply_text(tr("federations.it_doesn_t_look_like_you_have"))
    if not message.matches[0].group(1):
        return await message.reply_text(
            tr(
                "federations.need_give_federation_new_name_federation_names_can_up_64_characters_long"
            )
        )
    elif len(message.matches[0].group(1)) > 64:
        return await message.reply_text(
            tr("federations.federation_names_cannot_be_over_64_characters")
        )
    name = fedowner[1]
    fed_id = fedowner[0]
    new_name = message.text.split(None, 1)[1]
    await db.rename_fed(fed_id, new_name)
    final_text = tr(
        "federations.tada_ve_renamed_federation_from_fedid",
        name=name,
        new_name=new_name,
        fed_id=fed_id,
    )
    await message.reply_text(final_text)
    log_c = await db.get_fed_log(fed_id)
    if log_c and log_c != message.chat.id:
        await client.send_message(
            log_c,
            tr(
                "federations.federation_has_renamed",
                name=name,
                fed_id=fed_id,
                new_name=new_name,
                user_name=actor_user(message).first_name,
                user_id=actor_user(message).id,
            ),
        )


@command("joinfed", chat_scope="group", allow_connected=True)
async def jfed(client, message, sender_id: int = None, anon: bool = False):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title

    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "joinfed")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    if message.chat.type not in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
        ChatType.PRIVATE,
    ):
        return

    if not await is_chat_owner(message, user_id=sender_id, silent=False):
        return
    if not await bot_has_permission(
        message, chat_id=chat_id, privileges="can_restrict_members", silent=True
    ):
        return await message.reply_text(tr("federations.you_need_to_give_me_ban_rights"))
    args = message.matches[0].group(1)
    if not args:
        return await reply_usage(message)
    if len(args) < 10:
        return await message.reply_text(tr("federations.invalid_id"))
    getfed = await db.search_fed_by_id(args)
    if not getfed:
        return await message.reply_text(tr("federations.not_found"))
    name = getfed["fedname"]
    fed_id = await db.get_chat_fed(chat_id)
    if fed_id:
        await db.chat_leave_fed(fed_id, chat_id)
    if not await db.chat_join_fed(args, chat_id):
        return await message.reply_text(tr("federations.join_busy"))
    await message.reply_text(
        tr(
            "federations.successfully_joined_federation_all_new_federation_bans_will",
            name=name,
            title=title,
        )
    )
    log_c = await db.get_fed_log(args)
    if log_c and log_c != chat_id:
        await client.send_message(
            log_c,
            tr(
                "federations.chat_has_joined_federation",
                title=title,
                chat_id=chat_id,
                name=name,
                fed_id=fed_id,
            ),
        )


@command("leavefed", chat_scope="group", allow_connected=True)
async def lfed(client, message, sender_id: int = None, anon: bool = False):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "leavefed")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None

    if not await is_chat_owner(message, user_id=sender_id, silent=False):
        return
    fed_id = await db.get_chat_fed(chat_id)
    if fed_id:
        fed = await db.search_fed_by_id(fed_id)
        fname = fed.get("fedname", fed_id) if fed else fed_id
        await db.chat_leave_fed(fed_id, chat_id)
        await message.reply_text(
            tr("federations.chat_has_left_federation", title=title, fname=fname)
        )
    else:
        await message.reply_text(tr("federations.this_chat_isn_t_currently_in_any"))


@command("fpromote", chat_scope="group")
async def fp(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "fpromote")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    user = None
    try:
        user, extra = await get_user(message)
    except TypeError:
        pass
    if not user:
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(
            tr("federations.only_federation_creators_can_promote_people_and")
        )
    fname = fedowner[1]
    fed_id = fedowner[0]
    if user.id == sender_id:
        return await message.reply_text(tr("federations.yeah_well_you_are_the_fed_owner"))
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if fban:
        if fbanreason:
            reason = tr("federations.reason", fbanreason=html.escape(str(fbanreason)))
        else:
            reason = ""
        txt = tr(
            "federations.user_fbanned_should_unfban_them_before_promoting",
            user_id=user.id,
            user_name=html.escape(str(user.first_name)),
            fname=html.escape(str(fname)),
            reason=reason,
        )
        return await message.reply_text(txt, parse_mode=ParseMode.HTML)
    getuser = await db.search_user_in_fed(fed_id, user.id)
    if getuser:
        return await message.reply_text(
            tr(
                "federations.already_admin",
                user_id=user.id,
                user_name=html.escape(str(user.first_name)),
                fname=html.escape(str(fname)),
            ),
            parse_mode=ParseMode.HTML,
        )
    ftxt = tr(
        "federations.please_get_confirm_they_would_like_fed_admin",
        user_id=user.id,
        user_name=html.escape(str(user.first_name)),
        fname=html.escape(str(fname)),
    )
    await send_confirmation(
        message,
        ftxt,
        "fed_promote",
        {"fed_id": fed_id, "owner_id": sender_id, "user_id": user.id},
        [
            ("fp", tr("federations.accept"), ButtonStyle.SUCCESS),
            ("nofp", tr("federations.decline"), ButtonStyle.DANGER),
        ],
        client=client,
        users=[sender_id, user.id],
    )


@inline(pattern=r"fp(\_(.*))")
async def fp_cb(client, query):
    result = await _fed_confirmation(client, query, "fed_promote", role="user_id")
    if result is None:
        return
    data, fed = result
    fed_id, fname, user_id = data["fed_id"], fed["fedname"], data["user_id"]
    if (await db.get_fban_user(fed_id, user_id))[0]:
        return await query.answer(
            tr("federations.this_action_is_not_intended_for_you"), show_alert=True
        )
    name = (await client.get_users(user_id)).first_name
    if not await db.user_join_fed(fed_id, user_id, owner_id=data["owner_id"]):
        return await query.answer(
            tr("federations.this_federation_no_longer_exists"), show_alert=True
        )
    res = tr(
        "federations.user_now_admin",
        user_id=user_id,
        name=html.escape(str(name)),
        fname=html.escape(str(fname)),
        fed_id=fed_id,
    )
    await query.edit_message_text(res, parse_mode=ParseMode.HTML)
    await db.add_fname(user_id, query.from_user.first_name)


@inline(pattern=r"nofp(\_(.*))")
async def nofp(client, query):
    result = await _fed_confirmation(client, query, "fed_promote")
    if result is None:
        return
    data, _ = result
    owner_id, user_id = data["owner_id"], data["user_id"]
    if query.from_user.id == owner_id:
        user = await client.get_users(owner_id)
        await query.edit_message_text(
            tr(
                "federations.fedadmin_promotion_cancelled_by_a_href_tg",
                user_id=user.id,
                user_name=html.escape(str(user.first_name)),
            ),
            parse_mode=ParseMode.HTML,
        )
    elif query.from_user.id == user_id:
        user = await client.get_users(user_id)
        await query.edit_message_text(
            tr(
                "federations.fedadmin_promotion_has_been_refused_by_a",
                user_id=user.id,
                user_name=html.escape(str(user.first_name)),
            ),
            parse_mode=ParseMode.HTML,
        )
    else:
        await query.answer(tr("federations.you_are_not_the_user_being_fpromoted"))


@command("fdemote", chat_scope="group")
async def fd(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "fdemote")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    user = None
    try:
        user, extra = await get_user(message)
    except TypeError:
        pass
    if not user:
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(
            tr("federations.only_federation_creators_can_demote_people_and")
        )
    fname = fedowner[1]
    fed_id = fedowner[0]
    if not (await db.search_user_in_fed(fed_id, user.id)):
        return await message.reply_text(
            tr("federations.this_person_isn_t_a_federation_admin", fname=fname)
        )
    await db.user_demote_fed(fed_id, user.id)
    await message.reply_text(
        tr(
            "federations.user_no_longer_admin",
            user_id=user.id,
            user_name=html.escape(str(user.first_name)),
            fname=html.escape(str(fname)),
            fed_id=fed_id,
        ),
        parse_mode=ParseMode.HTML,
    )


@command(pattern="(ftransfer|fedtransfer)", chat_scope="group")
async def transfer_federation(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "ftransfer")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    user_r = None
    if not await is_user_admin(message, user_id=sender_id, silent=False):
        return
    try:
        user_r, extra = await get_user(message)
    except TypeError:
        pass
    if not user_r:
        return
    if user_r.bot:
        return await message.reply_text(tr("federations.bots_can_t_own_federations"))
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(tr("federations.you_don_t_have_a_fed_to"))
    fname = fedowner[1]
    fed_id = fedowner[0]
    if user_r.id == sender_id:
        return await message.reply_text(tr("federations.you_can_only_transfer_your_fed_to"))
    ownerfed = await db.get_user_owner_fed_full(user_r.id)
    if ownerfed:
        return await message.reply_text(
            tr(
                "federations.already_owns_federation_they_can_t_own_another",
                user_id=user_r.id,
                user_name=html.escape(str(user_r.first_name)),
            ),
            parse_mode=ParseMode.HTML,
        )
    getuser = await db.search_user_in_fed(fed_id, user_r.id)
    if not getuser:
        return await message.reply_text(
            tr(
                "federations.isn_t_admin_can_only_give_fed_other",
                user_id=user_r.id,
                user_name=html.escape(str(user_r.first_name)),
                fname=html.escape(str(fname)),
            ),
            parse_mode=ParseMode.HTML,
        )
    owner = await client.get_users(sender_id)
    text = tr(
        "federations.please_confirm_would_like_receive_fed_from",
        user_id=user_r.id,
        user_name=html.escape(user_r.first_name),
        fname=html.escape(fname),
        fed_id=fed_id,
        sender_id=sender_id,
        user_name_2=html.escape(owner.first_name),
    )
    await send_confirmation(
        message,
        text,
        "fed_transfer_accept",
        {"fed_id": fed_id, "owner_id": sender_id, "user_id": user_r.id},
        [
            ("ft", tr("federations.accept"), ButtonStyle.SUCCESS),
            ("noft", tr("federations.decline"), ButtonStyle.DANGER),
        ],
        client=client,
        users=[sender_id, user_r.id],
    )


@inline(pattern=r"ft(\_(.*))")
async def accept_federation_transfer(client, query):
    result = await _fed_confirmation(client, query, "fed_transfer_accept", role="user_id")
    if result is None:
        return
    data, fed = result
    owner_id = data["owner_id"]
    fed_id, fname = data["fed_id"], fed["fedname"]
    try:
        owner = await client.get_users(owner_id)
    except (RPCError, OSError):
        return
    e_text = tr(
        "federations.please_confirm_wish_send_fed_cannot_undone",
        user_id=owner.id,
        user_name=html.escape(str(owner.first_name)),
        fname=html.escape(str(fname)),
        fed_id=fed_id,
        user_id_2=query.from_user.id,
        user_name_2=html.escape(query.from_user.first_name),
    )
    from Emilia.utils.cb_token import stash

    cb_data = await stash(
        {"action": "fed_transfer_confirm", "data": data, "users": [owner_id]},
        ttl=900,
        client=client,
        chat_id=query.message.chat.id,
        message_id=query.message.id,
    )
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("federations.confirm"),
                    callback_data=f"ftc_{cb_data}",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    tr("buttons.cancel"),
                    callback_data=f"ftnoc_{cb_data}",
                    style=ButtonStyle.DEFAULT,
                ),
            ]
        ]
    )
    await query.edit_message_text(e_text, reply_markup=buttons, parse_mode=ParseMode.HTML)


@inline(pattern=r"noft(\_(.*))")
async def ft_decline(client, query):
    result = await _fed_confirmation(client, query, "fed_transfer_accept")
    if result is None:
        return
    data, _ = result
    owner_id, user_id = data["owner_id"], data["user_id"]
    user_name = html.escape(query.from_user.first_name)
    if query.from_user.id == owner_id:
        o_text = tr(
            "federations.has_cancelled_fed_transfer",
            owner_id=owner_id,
            user_name=user_name,
        )
    elif query.from_user.id == user_id:
        o_text = tr(
            "federations.has_declined_fed_transfer",
            owner_id=user_id,
            user_name=user_name,
        )
    await query.edit_message_text(o_text, parse_mode=ParseMode.HTML, reply_markup=None)


ftransfer_log = tr("federations.fed_transfer_fed_new_fed_owner_old_fed")


@inline(pattern=r"ftc(\_(.*))")
async def ft_confirm(client, query):
    result = await _fed_confirmation(client, query, "fed_transfer_confirm", role="owner_id")
    if result is None:
        return
    data, fed = result
    owner_id, user_id = data["owner_id"], data["user_id"]
    fed_id, fname = data["fed_id"], fed["fedname"]
    f_text = tr("federations.congratulations_federation_has_successfully_transferred_from")
    o_name = html.escape(query.from_user.first_name)
    n_name = html.escape((await client.get_users(user_id)).first_name)
    if await db.get_user_owner_fed_full(user_id) or not await db.transfer_fed(
        fed_id, owner_id, user_id
    ):
        return await query.answer(
            tr("federations.this_action_is_not_intended_for_you"), show_alert=True
        )
    await query.edit_message_text(
        f_text.format(html.escape(fname), fed_id, owner_id, o_name, user_id, n_name),
        parse_mode=ParseMode.HTML,
    )
    await query.message.answer(
        ftransfer_log.format(
            html.escape(fname),
            user_id,
            n_name,
            user_id,
            owner_id,
            o_name,
            owner_id,
            user_id,
            n_name,
        ),
        parse_mode=ParseMode.HTML,
    )


@inline(pattern=r"ftnoc(\_(.*))")
async def ft_cancel(client, query):
    result = await _fed_confirmation(client, query, "fed_transfer_confirm", role="owner_id")
    if result is None:
        return
    data, _ = result
    owner_id = data["owner_id"]
    await query.edit_message_text(
        tr(
            "federations.fed_transfer_has_been_cancelled_by_a",
            owner_id=owner_id,
            user_name=html.escape(str(query.from_user.first_name)),
        ),
        parse_mode=ParseMode.HTML,
    )


@command("fednotif", chat_scope="private")
async def fed_notif(client, message):
    parts = message.text.split(None, 1)
    args = parts[1] if len(parts) > 1 else ""
    fedowner = await db.get_user_owner_fed_full(actor_user(message).id)
    if not fedowner:
        return await message.reply_text(tr("federations.aren_t_creator_any_await_feds_act"))
    fname = fedowner[1]
    if not args:
        mode = await db.user_feds_report(actor_user(message).id)
        if mode:
            f_txt = tr("federations.fed_currently_sending_notifications_s_creator_when_fed")
        else:
            f_txt = tr("federations.fed_currently_not_sending_notifications_s_creator_when")
        await message.reply_text(f_txt.format(fname))
    elif args in ["on", "yes"]:
        await message.reply_text(
            tr("federations.fed_silence_setting_has_updated_true", fname=fname)
        )
        await db.set_feds_setting(actor_user(message).id, True)
    elif args in ["off", "no"]:
        await message.reply_text(
            tr("federations.fed_silence_setting_has_updated_false", fname=fname)
        )
        await db.set_feds_setting(actor_user(message).id, False)
    else:
        await message.reply_text(tr("errors.invalid_toggle"))


new_fban = tr("federations.new_fedban_fed_fedadmin_user_user_id")
update_fban = tr("federations.fedban_reason_update_fed_fedadmin_user_user_id")
un_fban = tr("federations.new_un_fedban_fed_fedadmin_user_user_id")


@command("fedreason", chat_scope="private")
async def fed_reason(client, message):
    parts = message.text.split(None, 1)
    args = parts[1] if len(parts) > 1 else ""
    fedowner = await db.get_user_owner_fed_full(actor_user(message).id)
    if not fedowner:
        return await message.reply_text(tr("federations.aren_t_creator_any_await_feds_act"))
    fname = fedowner[1]
    fed_id = fedowner[0]
    if not args:
        mode = await db.get_fed_reason(fed_id)
        if mode:
            f_txt = tr("federations.fed_currently_requiring_reason_fedbans")
        else:
            f_txt = tr("federations.fed_currently_not_requiring_reason_fedbans")
        await message.reply_text(f_txt.format(fname))
    elif args in ["on", "yes"]:
        await message.reply_text(tr("federations.fed_reason_setting_has_updated_true", fname=fname))
        await db.set_fed_reason(fed_id, True)
    elif args in ["off", "no"]:
        await message.reply_text(
            tr("federations.fed_reason_setting_has_updated_false", fname=fname)
        )
        await db.set_fed_reason(fed_id, False)
    else:
        await message.reply_text(tr("errors.invalid_toggle"))


@command("fban")
async def fban(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "fban")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        fed_id = await db.get_chat_fed(message.chat.id)
        if not fed_id:
            return await message.reply_text(tr("federations.chat_not_joined"))
        mejik = await db.search_fed_by_id(fed_id)
        fname = mejik["fedname"]
        if not (await is_user_fed_admin(fed_id, sender_id)):
            return await message.reply_text(
                tr("federations.you_aren_t_a_federation_admin_for", fname=fname)
            )
        owner_id = mejik["owner_id"]
    elif message.chat.type == ChatType.PRIVATE:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await message.reply_text(tr("federations.you_aren_t_the_creator_of_any"))
        fed_id = fedowner[0]
        fname = fedowner[1]
        owner_id = sender_id
    user = None
    reason = None
    try:
        user, reason = await get_user(message)
    except TypeError:
        pass
    if not user:
        return await reply_usage(message)
    check_reason = await db.get_fed_reason(fed_id)
    if check_reason:
        if not reason:
            return await reply_usage(message)
    if reason:
        if len(reason) > 1024:
            reason = reason[:1024] + tr(
                "federations.note_fban_reason_over_1024_characters_has_truncated"
            )
    else:
        reason = "None"
    if user.id in {Config.BOT_ID, bot_id(client)}:
        return await message.reply_text(tr("federations.oh_you_re_a_funny_one_aren"))
    elif user.id in ADMINS:
        return await message.reply_text(tr("federations.i_am_not_banning_my_developers"))
    elif await is_user_fed_admin(fed_id, user.id):
        f_ad = tr("federations.m_not_banning_fed_admin_owner_from_their", fname=fname)
        return await message.reply_text(f_ad)
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if fban:
        if reason == "" and fbanreason == "":
            return await message.reply_text(
                tr(
                    "federations.user_already_banned_there_no_reason_set_their",
                    user_id=user.id,
                    user_name=html.escape(str(user.first_name)),
                    fname=html.escape(str(fname)),
                ),
                parse_mode=ParseMode.HTML,
            )
        elif reason == fbanreason:
            return await message.reply_text(
                tr(
                    "federations.user_has_already_fbanned_exact_same_reason",
                    user_id=user.id,
                    user_name=html.escape(str(user.first_name)),
                ),
                parse_mode=ParseMode.HTML,
            )
        elif reason is None:
            if not fbanreason:
                return await message.reply_text(
                    tr(
                        "federations.user_already_banned",
                        user_id=user.id,
                        user_name=html.escape(str(user.first_name)),
                        fname=html.escape(str(fname)),
                    ),
                    parse_mode=ParseMode.HTML,
                )
            else:
                return await message.reply_text(
                    tr(
                        "federations.user_already_banned_reason",
                        user_id=user.id,
                        user_name=html.escape(str(user.first_name)),
                        fname=html.escape(str(fname)),
                        fbanreason=html.escape(str(fbanreason)),
                    ),
                    parse_mode=ParseMode.HTML,
                )
        await db.fban_user(
            fed_id,
            user.id,
            user.first_name,
            user.last_name,
            reason,
            datetime.now(UTC),
        )
        p_reason = ""
        if fbanreason:
            p_reason = tr("federations.previous_reason", fbanreason=html.escape(str(fbanreason)))
        fban_global_text = update_fban.format(
            html.escape(fname),
            sender_id,
            html.escape(actor_user(message).first_name),
            user.id,
            html.escape(user.first_name),
            user.id,
            p_reason,
            html.escape(reason),
        )
    else:
        await db.fban_user(
            fed_id,
            user.id,
            user.first_name,
            user.last_name,
            reason,
            datetime.now(UTC),
        )
        fban_global_text = new_fban.format(
            html.escape(fname),
            sender_id,
            html.escape(actor_user(message).first_name),
            user.id,
            html.escape(user.first_name),
            user.id,
            html.escape(reason),
        )
        if reason:
            fban_global_text = fban_global_text + f"<b>Reason:</b> {html.escape(reason)}"
    await message.answer(fban_global_text, parse_mode=ParseMode.HTML)
    getfednotif = await db.user_feds_report(int(owner_id))
    if getfednotif and message.chat.id != int(owner_id):
        await client.send_message(int(owner_id), fban_global_text, parse_mode=ParseMode.HTML)
    log_c = await db.get_fed_log(fed_id)
    if log_c and message.chat.id != int(log_c):
        await client.send_message(int(log_c), fban_global_text, parse_mode=ParseMode.HTML)
    fed_chats = list(await db.get_all_fed_chats(fed_id))
    if len(fed_chats) != 0:
        total = len(fed_chats)
        status = None
        last_edit = 0.0
        if total > 10:
            try:
                status = await message.answer(
                    tr("federations.propagating_ban_across_chats", total=total),
                )
            except (RPCError, OSError):
                status = None
        for idx, c in enumerate(fed_chats, start=1):
            try:
                await flood_safe(
                    lambda c=c: client.ban_chat_member(int(c), user.id, revoke_messages=True)
                )
            except (RPCError, OSError) as exc:
                LOGGER.warning(f"fban propagation failed for chat {c}: {exc}")
            # pace to stay under Telegram's global ceiling
            await asyncio.sleep(0.1)
            # Progress edit at most once per 2s (edit throttling).
            if status and idx % 10 == 0 and (asyncio.get_event_loop().time() - last_edit) > 2:
                last_edit = asyncio.get_event_loop().time()
                try:
                    await status.delete()
                except (RPCError, OSError):
                    pass
                try:
                    status = await message.answer(
                        tr("federations.propagating_ban_chats", idx=idx, total=total),
                    )
                except (RPCError, OSError):
                    pass
        if status:
            try:
                await status.delete()
            except (RPCError, OSError):
                pass
            try:
                status = await message.answer(
                    tr("federations.ban_propagated_chats", total=total),
                )
            except (RPCError, OSError):
                pass
    subs = list(await db.get_fed_subs(fed_id))
    if len(subs) != 0:
        for fed in subs:
            await db.fban_user(
                fed,
                user.id,
                user.first_name,
                user.last_name,
                reason,
                datetime.now(UTC),
            )
            all_fedschat = await db.get_all_fed_chats(fed)
            for c in all_fedschat:
                try:
                    await flood_safe(
                        lambda c=c: client.ban_chat_member(int(c), user.id, revoke_messages=True)
                    )
                except (RPCError, OSError) as exc:
                    LOGGER.warning(f"fban propagation (sub-fed {fed}) failed for chat {c}: {exc}")
                await asyncio.sleep(0.1)


@command("unfban")
async def unfban(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "unfban")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        fed_id = await db.get_chat_fed(message.chat.id)
        if not fed_id:
            return await message.reply_text(tr("federations.chat_not_joined"))
        mejik = await db.search_fed_by_id(fed_id)
        fname = mejik["fedname"]
        if not (await is_user_fed_admin(fed_id, sender_id)):
            return await message.reply_text(
                tr("federations.you_aren_t_a_federation_admin_for", fname=fname)
            )
        owner_id = mejik["owner_id"]
    elif message.chat.type == ChatType.PRIVATE:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await message.reply_text(tr("federations.aren_t_creator_any_await_feds_act"))
        fed_id = fedowner[0]
        fname = fedowner[1]
        owner_id = sender_id
    user = None
    reason = None
    try:
        user, reason = await get_user(message)
    except TypeError:
        pass
    if not user:
        return await reply_usage(message)
    if reason:
        if len(reason) > 1024:
            reason = reason[:1024] + tr(
                "federations.note_unfban_reason_over_1024_characters_has_truncated"
            )
    if user.id in {Config.BOT_ID, bot_id(client)}:
        return await message.reply_text(
            tr("federations.oh_re_funny_one_aren_t_how_do_think_would_have_fbanned_myself_hm")
        )
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, user.id)
    if not fban:
        g_string = tr(
            "federations.user_isn_t_banned_current_federation", fname=fname, fed_id=fed_id
        )
        return await message.reply_text(g_string)
    ufb_string = un_fban.format(
        html.escape(fname),
        sender_id,
        html.escape(actor_user(message).first_name),
        user.id,
        html.escape(user.first_name),
        user.id,
    )
    if reason:
        ufb_string = ufb_string + f"\n<b>Reason:</b> {html.escape(reason)}"
    await db.unfban_user(fed_id, user.id)
    await message.answer(ufb_string, parse_mode=ParseMode.HTML)
    getfednotif = await db.user_feds_report(int(owner_id))
    if getfednotif and message.chat.id != int(owner_id):
        await client.send_message(int(owner_id), ufb_string, parse_mode=ParseMode.HTML)
    log_c = await db.get_fed_log(fed_id)
    if log_c and message.chat.id != int(log_c):
        await client.send_message(int(log_c), ufb_string, parse_mode=ParseMode.HTML)


@command("chatfed", chat_scope="group", allow_connected=True)
async def CF(client, c):
    chat_id = effective_chat_id(c)
    title = effective_chat(c).title
    if not await is_user_admin(c, user_id=c.from_user.id if c.from_user else None, silent=False):
        return
    fed_id = await db.get_chat_fed(chat_id)
    if not fed_id:
        return await c.reply_text(tr("federations.this_chat_isn_t_part_of_any"))
    fname = (await db.search_fed_by_id(fed_id))["fedname"]
    c_f = tr(
        "federations.chat_part_following_federation_id", title=title, fname=fname, fed_id=fed_id
    )
    await c.reply_text(c_f)


fed_info = tr("federations.fed_info_fedid_name_creator_person_number_admins")


@command("fedinfo")
async def finfo(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "fedinfo")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not await is_user_admin(message, user_id=sender_id, silent=False):
            return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    parts = message.text.split(None, 1)
    input = parts[1] if len(parts) > 1 else ""
    if not input and not fedowner:
        return await reply_usage(message)
    elif input:
        if len(input) < 10:
            return await message.reply_text(tr("federations.invalid_id"))
        getfed = await db.search_fed_by_id(input)
        if not getfed:
            return await message.reply_text(tr("federations.not_found"))
        fname = getfed["fedname"]
        fed_id = input
    elif fedowner:
        fed_id = fedowner[0]
        fname = fedowner[1]
    info = await db.search_fed_by_id(fed_id)
    fadmins = len(info["fedadmins"])
    fbans = await db.get_len_fbans(fed_id)
    fchats = len(info["chats"])
    subbed = len(await db.get_fed_subs(fed_id))
    fed_main = fed_info.format(
        fed_id,
        html.escape(fname),
        int(info["owner_id"]),
        int(info["owner_id"]),
        fadmins,
        fbans,
        fchats,
        subbed,
    )
    x_sub = await db.get_my_subs(fed_id)
    if len(x_sub) == 0:
        fed_main = fed_main + tr("federations.federation_not_subscribed_any_other_await_feds")
    else:
        out_str = tr("federations.subscribed_following_await_feds")
        for x in x_sub:
            fname = (await db.search_fed_by_id(x))["fedname"]
            out_str += tr("federations.feds_fed_name_fed", fed_name=html.escape(str(fname)), fed=x)
        fed_main = fed_main + out_str
    buttons = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("federations.check_fed_admins"),
                    callback_data=f"check_fadmins_{fed_id}",
                )
            ]
        ]
    )
    await message.reply_text(fed_main, parse_mode=ParseMode.HTML, reply_markup=buttons)


@inline(pattern=r"check_fadmins(\_(.*))")
async def check_fadmins(client, e):
    if e.message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not await is_user_admin(e, user_id=actor_user(e).id):
            return
    fed_id = (e.matches[0].group(1)).split("_", 1)[1]
    x_admins = await db.get_all_fed_admins(fed_id) or []
    fname = (await db.search_fed_by_id(fed_id))["fedname"]
    out_str = tr("federations.admins_federation", fname=html.escape(fname))
    for _x in x_admins:
        _x_name = await db.get_fname(_x) or (await client.get_users(int(_x))).first_name
        out_str += tr(
            "federations.check_fadmins_user_id_x_name_user_id_2",
            user_id=_x,
            x_name=html.escape(str(_x_name)),
            user_id_2=_x,
        )
    await e.edit_message_reply_markup(reply_markup=None)
    await e.message.answer(out_str, parse_mode=ParseMode.HTML)


@command("subfed")
async def s_fed(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "subfed")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(
            tr("federations.only_federation_creators_can_subscribe_to_a")
        )
    parts = message.text.split(None, 1)
    arg = parts[1] if len(parts) > 1 else ""
    if not arg:
        return await reply_usage(message)
    if len(arg) < 10:
        return await message.reply_text(tr("federations.invalid_id"))
    getfed = await db.search_fed_by_id(arg)
    if not getfed:
        return await message.reply_text(tr("federations.not_found"))
    s_fname = getfed["fedname"]
    if arg == fedowner[0]:
        return await message.reply_text(tr("federations.what_s_the_point_in_subscribing_a"))
    if len(await db.get_my_subs(str(fedowner[0]))) >= Config.FEDERATION_MAX_SUBSCRIPTIONS:
        return await message.reply_text(
            tr("federations.subscription_limit", limit=Config.FEDERATION_MAX_SUBSCRIPTIONS)
        )
    if not await db.sub_fed(arg, fedowner[0]):
        return await message.reply_text(tr("federations.subscription_busy"))
    await message.reply_text(
        tr(
            "federations.federation_has_now_subscribed_all_fedbans_will_now",
            fedowner=fedowner[1],
            s_fname=s_fname,
            s_fname_2=s_fname,
        )
    )


@command("unsubfed")
async def us_fed(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "unsubfed")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(
            tr("federations.only_federation_creators_can_unsubscribe_to_a")
        )
    parts = message.text.split(None, 1)
    arg = parts[1] if len(parts) > 1 else ""
    if not arg:
        return await reply_usage(message)
    if len(arg) < 10:
        return await message.reply_text(tr("federations.invalid_id"))
    getfed = await db.search_fed_by_id(arg)
    if not getfed:
        return await message.reply_text(tr("federations.not_found"))
    await message.reply_text(
        tr("federations.federation_no_longer_subscribed_bans_will_no_longer").format(
            fedowner[1], getfed["fedname"], getfed["fedname"]
        )
    )
    await db.unsub_fed(arg, fedowner[0])


@command(pattern="(feddemoteme|fdemoteme)")
async def self_demote(client, e, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(e):
            return await anon_fed(e, "feddemoteme")
    if not sender_id:
        sender_id = actor_user(e).id if actor_user(e) else None
    try:
        fed_id = e.text.split(None, 1)[1]
    except IndexError:
        return await reply_usage(e)
    getfed = await db.search_fed_by_id(fed_id)
    if not getfed:
        return await e.reply_text(tr("federations.not_found"))
    fedname = getfed["fedname"]
    if int(getfed["owner_id"]) == sender_id:
        return await e.reply_text(tr("federations.you_can_t_demote_yourself_from_your"))
    if not (await is_user_fed_admin(fed_id, sender_id)):
        return await e.reply_text(tr("federations.aren_t_admin_how_would_demote", fedname=fedname))
    await e.reply_text(tr("federations.you_are_no_longer_a_fed_admin", fedname=fedname))
    await db.user_demote_fed(fed_id, sender_id)


@command("myfeds")
async def my_feds(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "myfeds")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    fed_list = await db.get_all_fed_admin(
        actor_user(message).id if actor_user(message) else sender_id
    )
    if not fed_list:
        return await message.reply_text(tr("federations.you_aren_t_a_member_of_any"))
    out_str = tr("federations.admin_following_federations")
    for fed in fed_list:
        fed_name = await db.get_fed_name(fed)
        out_str += tr("federations.feds_fed_name_fed", fed_name=html.escape(str(fed_name)), fed=fed)
    await message.reply_text(out_str)


@command("setfedlog", chat_scope="group_or_channel", allow_connected=True)
@anonadmin_checker(named=True)
async def set_fed_logs(client, e, sender_id: int = None, anon: bool = False):
    if not anon:
        if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and not actor_user(e):
            return await anon_fed(e, "setfedlog")
    if not sender_id:
        sender_id = actor_user(e).id if actor_user(e) else None
    if not await check_user(e, user_id=sender_id, privileges="can_change_info"):
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await e.reply_text(tr("federations.only_fed_creators_can_set_a_fed"))
    fed_id, fname = fedowner[:2]
    requested_id = (e.command[1] if len(e.command or []) > 1 else "").strip()
    if requested_id and requested_id != fed_id:
        return await e.reply_text(tr("federations.this_isn_t_a_valid_fedid"))
    if not await bot_has_permission(
        e,
        privileges="can_post_messages"
        if effective_chat(e).type == ChatType.CHANNEL
        else "can_change_info",
    ):
        return
    await db.set_fed_log(fed_id, effective_chat_id(e))
    await e.reply_text(tr("federations.this_has_been_set_as_the_fed", fname=fname))


@command("unsetfedlog", chat_scope="group_or_channel", allow_connected=True)
@anonadmin_checker(named=True)
async def un_set_fed_log(client, e, sender_id: int = None, anon: bool = False):
    if not anon:
        if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and not actor_user(e):
            return await anon_fed(e, "unsetfedlog")
    if not sender_id:
        sender_id = actor_user(e).id if actor_user(e) else None
    if not await check_user(e, user_id=sender_id, privileges="can_change_info"):
        return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await e.reply_text(tr("federations.only_fed_creators_can_unset_a_fed"))
    fed_id = fedowner[0]
    fname = fedowner[1]
    await db.set_fed_log(fed_id)
    await e.reply_text(tr("federations.federation_has_had_its_log_location_unset", fname=fname))


@command("fedadmins")
async def fedadmins_(client, e, sender_id: int = None, anon: bool = False):
    if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not anon:
            if not actor_user(e):
                return await anon_fed(e, "fedadmins")
        if not sender_id:
            sender_id = actor_user(e).id if actor_user(e) else None
        if not await is_user_admin(e, user_id=sender_id, silent=False):
            return
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner and not e.matches[0].group(1):
        return await reply_usage(e)
    elif fedowner:
        fed_id = fedowner[0]
        fname = fedowner[1]
    elif len(e.text.split(" ", 1)) == 2:
        fed_id = e.text.split(" ", 1)[1]
        fed = await db.search_fed_by_id(fed_id)
        if not fed:
            return await e.reply_text(tr("federations.this_isn_t_a_valid_fedid"))
        fname = fed["fedname"]
    else:
        fed_id = await db.get_chat_fed(e.chat.id)
        if not fed_id:
            return await e.reply_text(tr("federations.chat_not_joined"))
        fname = (await db.search_fed_by_id(fed_id))["fedname"]
    x_admins = await db.get_all_fed_admins(fed_id) or []
    out_str = tr("federations.admins_federation_fedadmins", fname=html.escape(fname))
    for _x in x_admins:
        _x_name = await db.get_fname(_x) or (await client.get_users(int(_x))).first_name
        out_str += tr(
            "federations.check_fadmins_user_id_x_name_user_id_2",
            user_id=_x,
            x_name=html.escape(str(_x_name)),
            user_id_2=_x,
        )
    await e.reply_text(out_str, parse_mode=ParseMode.HTML)


@command("fedsubs")
async def fedsubs(client, message, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(message):
            return await anon_fed(message, "fedsubs")
    if not sender_id:
        sender_id = actor_user(message).id if actor_user(message) else None
    fedowner = await db.get_user_owner_fed_full(sender_id)
    if not fedowner:
        return await message.reply_text(tr("federations.aren_t_creator_any_await_feds_act"))
    subfed = await db.get_my_subs(fedowner[0])
    fname = fedowner[1]
    if not subfed:
        return await message.reply_text(tr("federations.you_aren_t_subscribed_to_any_other"))
    out_str = tr(
        "federations.federation_subscribed_following_feds", fname=fname, fedowner=fedowner[0]
    )
    for fed in subfed:
        fed_name = await db.get_fed_name(fed)
        out_str += f"\n- {fed_name} (`{fed}`)"
    await message.reply_text(out_str)


@command("fedstat")
async def fedstat(client, e, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(e):
            return await anon_fed(e, "fedstat")
    if not sender_id:
        sender_id = actor_user(e).id if actor_user(e) else None
    if not e.matches[0].group(1):
        return await reply_usage(e)
    getfed = await db.search_fed_by_id(e.matches[0].group(1))
    if not getfed:
        return await e.reply_text(tr("federations.not_found"))
    fban, fbanreason, fbantime = await db.get_fban_user(e.matches[0].group(1), sender_id)
    if not fban:
        return await e.reply_text(tr("federations.you_aren_t_banned_in_this_federation"))
    out_str = tr(
        "federations.banned_federation",
        fedname=getfed["fedname"],
        federation_id=e.matches[0].group(1),
    )
    if fbanreason:
        out_str += f"\nReason: {fbanreason}"
    out_str += f"\nTime: {fbantime}"
    await e.reply_text(out_str)


@command(pattern="(fexport|fedexport)")
async def fed_export___(client, e, sender_id: int = None, anon: bool = False):
    if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        if not anon:
            if not actor_user(e):
                return await anon_fed(e, "fexport")
        if not sender_id:
            sender_id = actor_user(e).id if actor_user(e) else None
        fed_id = await db.get_chat_fed(e.chat.id)
        if not fed_id:
            return await e.reply_text(tr("federations.chat_not_joined"))
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner or fedowner[0] != fed_id:
            return await e.reply_text(tr("federations.only_the_fed_creator_can_export_the"))
        fname = fedowner[1]
    elif e.chat.type == ChatType.PRIVATE:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await e.reply_text(tr("federations.aren_t_creator_any_await_feds_act"))
        fname = fedowner[1]
        fed_id = fedowner[0]
    fbans = await db.get_all_fbans(fedowner[0])
    if not fbans:
        return await e.reply_text(tr("federations.there_no_banned_users", fname=fname))
    if not len(e.text.split(" ", 1)) == 2:
        mode = "csv"
    elif len(e.text.split(" ", 1)) == 2:
        pc = e.text.split(" ", 1)[1].lower()
        if pc not in ["csv", "json", "xml"]:
            mode = "csv"
        else:
            mode = pc
    else:
        mode = "csv"
    # Unique-per-call filename so concurrent exports (different feds/users)
    # can't race/overwrite each other's file; cleaned up after sending.
    export_path = f"fbanned_users_{uuid.uuid4().hex}.{mode}"
    try:
        if mode == "csv":
            fban_list = []
            for fban in fbans:
                fb = fbans[fban]
                fban_list.append(
                    {
                        "Name": fb[0],
                        "User ID": fban,
                        "Reason": fb[2],
                        "Time": str(fb[3]),
                    }
                )
            csv_headers = ["Name", "User ID", "Reason", "Time"]

            def _write_csv():
                with open(export_path, "w") as csvfile:
                    w = csv.DictWriter(csvfile, fieldnames=csv_headers)
                    w.writeheader()
                    for fban in fban_list:
                        w.writerow(fban)

            await asyncio.to_thread(_write_csv)
            await e.reply_document(
                export_path, caption=tr("federations.fbanned_users", fname=fname)
            )
        elif mode == "json":
            fban_list = ""
            for fban in fbans:
                fb = fbans[fban]
                json_p = {
                    "name": fb[0],
                    "user_id": fban,
                    "reason": fb[2],
                    "time": str(fb[3]),
                }
                fban_list += orjson.dumps(json_p).decode("utf-8") + "\n"
            await asyncio.to_thread(Path(export_path).write_text, fban_list, encoding="utf-8")
            await e.reply_document(
                export_path, caption=tr("federations.fbanned_users", fname=fname)
            )
        elif mode == "xml":
            fban_list = []
            for fban in fbans:
                fb = fbans[fban]
                fban_list.append(
                    {
                        "Name": fb[0],
                        "User ID": fban,
                        "Reason": fb[2],
                        "Time": str(fb[3]),
                    }
                )
            xml_str = ""
            qp = 0
            for x in fban_list:
                el = Element("fban")
                qp += 1
                el.set("sn", str(qp))
                for c, v in x.items():
                    child = Element(str(c))
                    child.text = str(v)
                    el.append(child)
                xml_str += tostring(el, encoding="unicode") + "\n"
            await asyncio.to_thread(Path(export_path).write_text, xml_str, encoding="utf-8")
            await e.reply_document(
                export_path, caption=tr("federations.fbanned_users", fname=fname)
            )
    finally:
        try:
            os.remove(export_path)
        except OSError:
            pass


@command(pattern="(fimport|fedimport)")
async def fed_import___(client, e, sender_id: int = None, anon: bool = False):
    if not anon:
        if not actor_user(e):
            return await anon_fed(e, "fimport")
    if not sender_id:
        sender_id = actor_user(e).id if actor_user(e) else None
    if not e.reply_to_message_id:
        return await reply_usage(e)
    r = e.reply_to_message
    r_ext = os.path.splitext(r.document.file_name or "")[1].lower() if r and r.document else None
    if r_ext not in [".xml", ".json", ".csv"]:
        return await reply_usage(e)
    if e.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        fed_id = await db.get_chat_fed(e.chat.id)
        if not fed_id:
            return await e.reply_text(tr("federations.chat_not_joined"))
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner or fedowner[0] != fed_id:
            return await e.reply_text(tr("federations.only_the_fed_creator_can_import_a"))
    elif e.chat.type == ChatType.PRIVATE:
        fedowner = await db.get_user_owner_fed_full(sender_id)
        if not fedowner:
            return await e.reply_text(tr("federations.aren_t_creator_any_await_feds_act"))
        fed_id = fedowner[0]
    if r_ext == ".xml":
        await e.reply_text(tr("federations.xml_import_unsupported"))
        return
    if r.document.file_size > MAX_IMPORT_BYTES:
        await e.reply_text(tr("federations.import_limit"))
        return
    async with asyncio.timeout(60):
        document = await r.download(in_memory=True)
    if document is None:
        return
    with document:
        if document.getbuffer().nbytes > MAX_IMPORT_BYTES:
            await e.reply_text(tr("federations.import_limit"))
            return
        try:
            fbans = await asyncio.to_thread(_read_import, document.getvalue(), r_ext[1:])
        except (ValueError, UnicodeDecodeError, csv.Error):
            await e.reply_text(tr("federations.invalid_import"))
            return
    imported = 0
    for row in fbans:
        imported += bool(
            await db.fban_user(
                fed_id, row["user_id"], row["name"], "", row["reason"], datetime.now(UTC)
            )
        )
    await e.reply_text(
        tr(
            "federations.files_were_imported_successfully_people_banned_failed_import",
            fbans=imported,
            files_were_imported=len(fbans) - imported,
        )
    )


async def anon_fed(message, mode):
    handlers = {
        "fimport": fed_import___,
        "fexport": fed_export___,
        "fedstat": fedstat,
        "fedsubs": fedsubs,
        "fedadmins": fedadmins_,
        "unsetfedlog": un_set_fed_log,
        "setfedlog": set_fed_logs,
        "myfeds": my_feds,
        "feddemoteme": self_demote,
        "subfed": s_fed,
        "unsubfed": us_fed,
        "fedinfo": finfo,
        "unfban": unfban,
        "fban": fban,
        "ftransfer": transfer_federation,
        "fdemote": fd,
        "fpromote": fp,
        "leavefed": lfed,
        "joinfed": jfed,
    }
    handler = handlers.get(mode)
    if handler is None:
        return

    async def invoke(client, source):
        return await handler(client, source, actor_id(source), anon=True)

    return await anonadmin_checker(named=True)(invoke)(message._client, message)


@command("quietfed", chat_scope="group", allow_connected=True)
@log_to_channel
async def qf(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title
    if not await is_user_admin(
        message,
        user_id=actor_user(message).id if actor_user(message) else None,
        silent=False,
    ):
        return

    data = await db.feds.find_one({"chat_id": chat_id})
    if data and data["quiet"]:
        # db is the feds_db module; quietfed() is the helper that upserts
        # feds.quiet
        await db.quietfed(chat_id, False)
        await message.reply_text(tr("federations.quietfed_has_disabled", title=title))
        return "QUIETFED_DISABLE", None, None
    else:
        await db.quietfed(chat_id, True)
        await message.reply_text(tr("federations.quietfed_has_enabled", title=title))
        return "QUIETFED_ENABLE", None, None


@listen()
async def fban_welcome(client, message):
    if not actor_user(message) or not (message.text or message.caption):
        return
    if message.chat.type == ChatType.PRIVATE:
        return
    if not await bot_has_permission(message, privileges="can_restrict_members", silent=True):
        return
    fed_id = await db.get_chat_fed(message.chat.id)
    if not fed_id:
        return
    fban, fbanreason, fbantime = await db.get_fban_user(fed_id, actor_user(message).id)
    quiet = await db.feds.find_one({"chat_id": message.chat.id})
    if fban and fbanreason:
        try:
            await client.ban_chat_member(message.chat.id, int(actor_user(message).id))
            if not quiet or quiet.get("quiet") is False:
                return await message.answer(
                    tr(
                        "federations.user_has_fbanned_current_federation_due_following_reason",
                        user_name=actor_user(message).first_name,
                        fbanreason=fbanreason,
                    ),
                )
            else:
                return
        except (RPCError, OSError) as exc:
            LOGGER.warning(f"fban_welcome ban_chat_member failed in {message.chat.id}: {exc}")
    else:
        return
