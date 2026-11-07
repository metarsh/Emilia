import html

from pyrogram.enums import ButtonStyle, ParseMode
from pyrogram.types import ReplyParameters

from Emilia.custom_filter import callbackquery as inline
from Emilia.custom_filter import command
from Emilia.database.approval import (
    approve_user,
    delete_all_approvals,
    get_approved_users,
    is_approved,
    unapprove_user,
)
from Emilia.locales import tr
from Emilia.utils.admins import get_user_reason
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_user, has_chat_permission, is_user_admin
from Emilia.utils.confirmation import authorize_chat_confirmation, send_confirmation
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.message_actor import actor_id, actor_user


@command("approve", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def appr(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title

    sender_id = actor_id(message)
    if not await check_user(
        message, chat_id=chat_id, user_id=sender_id, privileges="can_restrict_members"
    ):
        return
    user, reason = await get_user_reason(message)
    if not user:
        return await message.reply_text(tr("errors.user_not_found"))
    if await is_user_admin(message, user_id=user.id, silent=True):
        return await message.reply_text(tr("permissions.cannot_target_admin"))
    await approve_user(chat_id, int(user.id), user.first_name)
    a_str = tr("approval.has_approved_they_will_now_ignored_automated_admin")
    await message.answer(
        a_str.format(user.id, html.escape(user.first_name), html.escape(title)),
        reply_parameters=ReplyParameters(message_id=message.reply_to_message_id or message.id),
        parse_mode=ParseMode.HTML,
    )
    return "APPROVE", user.id, user.first_name


@command("unapprove", chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def dissapprove(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title
    sender_id = actor_id(message)
    if not await check_user(
        message, chat_id=chat_id, user_id=sender_id, privileges="can_restrict_members"
    ):
        return
    user, reason = await get_user_reason(message)
    if not user:
        return await message.reply_text(tr("errors.user_not_found"))
    if await is_user_admin(message, user_id=user.id, silent=True):
        return await message.reply_text(tr("permissions.cannot_target_admin"))
    if await unapprove_user(chat_id, int(user.id)):
        await message.reply_text(
            tr("approval.no_longer_approved", user_name=user.first_name, title=title)
        )
        return "DISAPPROVE", user.id, user.first_name
    await message.reply_text(tr("approval.isn_t_approved_yet", user_name=user.first_name))


@command("approved", chat_scope="group", allow_connected=True)
async def approved(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title
    app_rove_d = get_approved_users(chat_id)
    out_str = tr("approval.no_users_approved", title=title)
    async for app in app_rove_d:
        out_str += "\n- `{}`: {}".format(app["user_id"], app["name"])
    await message.reply_text(out_str)


@command("approval", chat_scope="group", allow_connected=True)
async def check_approval(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title

    if not message.reply_to_message and len(message.command or []) < 2:
        if actor_user(message) is None:
            return await message.reply_text(tr("approval.you_are_an_anonymous_user_or_a"))
        user = actor_user(message)
    else:
        user, xtra = await get_user_reason(message)
        if not user:
            return

    if await is_approved(chat_id, int(user.id), fresh=True):
        await message.reply_text(
            tr(
                "approval.approved_user_locks_antiflood_blocklists_won_t_apply",
                user_name=user.first_name,
                title=title,
            )
        )
    else:
        await message.reply_text(
            tr(
                "approval.not_approved_user_they_affected_normal_commands",
                user_name=user.first_name,
                title=title,
            )
        )


@command("unapproveall", chat_scope="group", allow_connected=True)
@anonadmin_checker(owner_only=True)
async def unapprove_all(client, message):
    chat_id = effective_chat_id(message)
    title = effective_chat(message).title

    sender_id = actor_id(message)
    if not await has_chat_permission(client, chat_id, sender_id, owner=True):
        return await message.reply_text(tr("permissions.owner_required"))
    await _confirm_unapprove(client, message, chat_id, title)


async def _confirm_unapprove(client, message, chat_id, title):
    await send_confirmation(
        message,
        tr(
            "approval.unapprove_all_users_action_cannot_undone",
            unapprove_all_users=html.escape(title or str(chat_id)),
        ),
        "unapprove_all",
        {"chat_id": chat_id},
        [
            ("unapproveyes", tr("approval.unapprove_all_users"), ButtonStyle.DANGER),
            ("unapproveno", tr("buttons.cancel"), ButtonStyle.DEFAULT),
        ],
        client=client,
    )


@inline(pattern=r"^unapproveyes_")
async def un_app(client, query):
    data = await authorize_chat_confirmation(client, query, "unapprove_all", owner=True)
    if data is None:
        return
    await delete_all_approvals(data["chat_id"])
    await query.edit_message_text(tr("approval.unapproved_all_users_in_chat_all_users"))


@inline(pattern=r"^unapproveno_")
async def c_un_ap(client, query):
    if await authorize_chat_confirmation(client, query, "unapprove_all", owner=True) is None:
        return
    await query.edit_message_text(tr("approval.unapproval_of_all_approved_users_has_been"))
