from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery

from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.confirmation import authorize_chat_confirmation, send_confirmation
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess


@command("unpinall", allow_connected=True, chat_scope="group")
@anonadmin_checker
async def unpinall(client, message):
    chat_id = effective_chat_id(message)
    if not await user_has_permission(message, privileges="can_pin_messages", silent=True):
        return await message.reply(tr("unpinall.you_don_t_have_permission_to_use"))
    await send_confirmation(
        message,
        tr("unpinall.are_you_sure_you_want_to_unpin"),
        "unpin_all",
        {"chat_id": chat_id},
        [
            ("unpinyes", tr("buttons.yes"), ButtonStyle.DANGER),
            ("unpinno", tr("buttons.no"), ButtonStyle.DEFAULT),
        ],
        client=client,
    )


@callbackquery(filters=filters.regex("^unpin(?:yes|no)_"), access=CallbackAccess(public=True))
async def unpinall_callback(client: Client, callback_query: CallbackQuery):
    data = await authorize_chat_confirmation(
        client, callback_query, "unpin_all", privilege="can_pin_messages"
    )
    if data is None:
        return
    if callback_query.data.startswith("unpinyes_"):
        await client.unpin_all_chat_messages(data["chat_id"])
        text = tr("unpinall.all_pinned_messages_have_been_unpinned")
    else:
        text = tr("clone.cancelled")
    await callback_query.message.edit_text(text)
