from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.locales import tr
from Emilia.utils.cb_token import stash, unstash
from Emilia.utils.menu_guard import CallbackAccess


async def authorize_chat_confirmation(client, query, action, *, owner=False, privilege=None):
    data = await read_confirmation(client, query, action)
    if data is None:
        return None
    if not await CallbackAccess(chat_id=data["chat_id"], owner=owner, privilege=privilege).allows(
        client, query
    ):
        return None
    return (
        data if await read_confirmation(client, query, action, consume=True) is not None else None
    )


async def send_confirmation(message, text, action, data, choices, *, client, users=None):
    sent = await message.answer(text, parse_mode=ParseMode.HTML)
    token = await stash(
        {"action": action, "data": data, "users": users},
        ttl=900,
        client=client,
        chat_id=sent.chat.id,
        message_id=sent.id,
    )
    await sent.edit_reply_markup(
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(label, callback_data=f"{prefix}_{token}", style=style)
                    for prefix, label, style in choices
                ]
            ]
        )
    )
    return sent


async def read_confirmation(client, query, action, *, consume=False):
    if not await CallbackAccess(public=True).allows(client, query):
        return None
    token = (query.data or "").split("_", 1)[-1]
    context = {"client": client, "chat_id": query.message.chat.id, "message_id": query.message.id}
    record = await unstash(token, **context)
    if (
        not isinstance(record, dict)
        or record.get("action") != action
        or (record.get("users") is not None and query.from_user.id not in record["users"])
    ):
        await query.answer(tr("custom_filter.this_button_has_expired"), show_alert=True)
        return None
    if consume and await unstash(token, consume=True, **context) is None:
        await query.answer(tr("custom_filter.this_button_has_expired"), show_alert=True)
        return None
    return record["data"]
