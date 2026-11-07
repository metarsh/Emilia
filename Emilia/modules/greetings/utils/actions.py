from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardMarkup

from Emilia.database.federations import get_chat_fed, get_fban_user
from Emilia.database.welcome import (
    AppendVerifiedUsers,
    DeleteUsercaptchaData,
)
from Emilia.services.captcha import is_current
from Emilia.utils.client_context import bot_id
from Emilia.utils.restrictions import restrict_member


async def remove_captcha_button(client, chat_id, message_id, token):
    """Keep the welcome's existing links when its verification button expires."""
    if not message_id:
        return
    try:
        message = await client.get_messages(chat_id, message_id)
        if not message.reply_markup:
            return
        rows = []
        for row in message.reply_markup.inline_keyboard:
            kept = [
                button
                for button in row
                if not (
                    button.callback_data == f"captcha_{token}"
                    or (
                        button.url
                        and "?start=captcha_" in button.url
                        and button.url.endswith(f"_{token}")
                    )
                )
            ]
            if kept:
                rows.append(kept)
        await client.edit_message_reply_markup(
            chat_id, message_id, reply_markup=InlineKeyboardMarkup(rows) if rows else None
        )
    except RPCError:
        pass


async def passedAction(
    client, chat_id: int, user_id: int, message_id: int, *, source="member", challenge=None
):
    fed_id = await get_chat_fed(chat_id)
    if fed_id and (await get_fban_user(fed_id, user_id))[0]:
        raise ValueError("A federation-banned user cannot complete verification")
    if source == "join_request":
        from Emilia.database.autoapprove import get_autoapprove_mode
        from Emilia.modules.autoapprove import check_cas

        mode = await get_autoapprove_mode(chat_id)
        expected = "rules" if challenge and challenge.get("mode") == "rules" else "captcha"
        if (
            mode not in {"captcha", "rules"}
            or (challenge and "mode" in challenge and mode != expected)
            or await check_cas(user_id) is not False
        ):
            raise ValueError("This join request requires administrator review")
        if challenge and not await is_current(challenge):
            raise ValueError("This CAPTCHA is no longer active")
        await client.approve_chat_join_request(chat_id, user_id)
    else:
        member = await client.get_chat_member(chat_id, user_id)
        if member.status not in {ChatMemberStatus.MEMBER, ChatMemberStatus.RESTRICTED}:
            raise ValueError("This CAPTCHA no longer applies to the member")
        if member.status == ChatMemberStatus.RESTRICTED:
            restricted_by = getattr(member, "restricted_by", None)
            if restricted_by and restricted_by.id != bot_id(client):
                raise ValueError("An administrator changed this member's restrictions")
            chat = await client.get_chat(chat_id)
            permissions = chat.permissions
            if permissions is None:
                raise ValueError("The group's default permissions are unavailable")
        if challenge and not await is_current(challenge):
            raise ValueError("This CAPTCHA is no longer active")
        if member.status == ChatMemberStatus.RESTRICTED:
            await restrict_member(
                chat_id,
                user_id,
                can_send_messages=True,
                client=client,
                permissions=permissions,
            )
    await AppendVerifiedUsers(chat_id, user_id)
    await DeleteUsercaptchaData(chat_id, user_id)
    if challenge:
        await remove_captcha_button(client, chat_id, message_id, challenge["token"])


async def failedAction(
    client, message, user_id: int, chat_id: int, message_id: int, *, source="member", challenge=None
):
    if source == "join_request":
        if challenge and not await is_current(challenge):
            return
        await client.decline_chat_join_request(chat_id, user_id)
        return
    member = await client.get_chat_member(chat_id, user_id)
    restricted_by = getattr(member, "restricted_by", None)
    if member.status != ChatMemberStatus.RESTRICTED or (
        restricted_by and restricted_by.id != bot_id(client)
    ):
        return
    if challenge and not await is_current(challenge):
        return
    await client.ban_chat_member(chat_id, user_id)
    await client.unban_chat_member(chat_id, user_id)
    if challenge:
        await remove_captcha_button(client, chat_id, message_id, challenge["token"])
