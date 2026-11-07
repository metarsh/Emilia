import html

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery

from Emilia.custom_filter import callbackquery, command
from Emilia.database.blocklists import get_blocklist, unblocklistall_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import has_chat_permission
from Emilia.utils.confirmation import authorize_chat_confirmation, send_confirmation
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_id


@command(["unblocklistall", "unblacklistall"], allow_connected=True, chat_scope="group")
@anonadmin_checker(owner_only=True)
async def removeblocklistall(client, message):
    chat_id = effective_chat_id(message)
    user_id = actor_id(message)
    if not await has_chat_permission(client, chat_id, user_id, owner=True):
        return await message.reply(tr("unblocklistall.you_re_not_owner_of_this_chat"))
    title = effective_chat(message).title or str(chat_id)
    if not await get_blocklist(chat_id):
        return await message.reply(
            tr("unblocklistall.no_blocklist_filters_active", title=html.escape(title))
        )
    await send_confirmation(
        message,
        tr("unblocklistall.are_you_sure_you_would_like_to", title=html.escape(title)),
        "clear_blocklists",
        {"chat_id": chat_id},
        [
            (
                "blocklistsy",
                tr("unblocklistall.delete_blocklist"),
                ButtonStyle.DANGER,
            ),
            ("blocklistsn", tr("buttons.cancel"), ButtonStyle.DEFAULT),
        ],
        client=client,
    )


@callbackquery(filters=filters.regex("^blocklists[yn]_"), access=CallbackAccess(public=True))
async def removeblocklistall_callback(client: Client, callback_query: CallbackQuery):
    data = await authorize_chat_confirmation(client, callback_query, "clear_blocklists", owner=True)
    if data is None:
        return
    if callback_query.data.startswith("blocklistsy_"):
        await unblocklistall_db(data["chat_id"])
        text = tr("unblocklistall.deleted_chat_blocklist")
    else:
        text = tr("clone.cancelled")
    await callback_query.message.edit_text(text)
