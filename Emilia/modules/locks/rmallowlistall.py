import html

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery

from Emilia.custom_filter import callbackquery, command
from Emilia.database.locks import rmallowall_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import has_chat_permission
from Emilia.utils.confirmation import authorize_chat_confirmation, send_confirmation
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_id


@command("rmallowlistall", allow_connected=True, chat_scope="group")
async def rmallowlistall(client, message):
    chat_id = effective_chat_id(message)
    user_id = actor_id(message)
    if not await has_chat_permission(client, chat_id, user_id):
        return await message.reply(tr("rmallowlistall.you_are_not_allowed_to_do_that"))
    title = effective_chat(message).title or str(chat_id)
    await send_confirmation(
        message,
        tr("rmallowlistall.are_you_sure_you_would_like_to", title=html.escape(title)),
        "clear_allowlist",
        {"chat_id": chat_id},
        [
            (
                "allowlisty",
                tr("rmallowlistall.delete_allowlist"),
                ButtonStyle.DANGER,
            ),
            ("allowlistn", tr("buttons.cancel"), ButtonStyle.DEFAULT),
        ],
        client=client,
    )


@callbackquery(filters=filters.regex("^allowlist[yn]_"), access=CallbackAccess(public=True))
async def rmallowlistall_callback(client: Client, callback_query: CallbackQuery):
    data = await authorize_chat_confirmation(client, callback_query, "clear_allowlist")
    if data is None:
        return
    if callback_query.data.startswith("allowlisty_"):
        await rmallowall_db(data["chat_id"])
        text = tr("rmallowlistall.delete_chat_allowlist")
    else:
        text = tr("clone.cancelled")
    await callback_query.message.edit_text(text)
