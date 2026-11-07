import html

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery

from Emilia.custom_filter import callbackquery, command
from Emilia.database.warnings import reset_all_warns_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import has_chat_permission
from Emilia.utils.confirmation import authorize_chat_confirmation, send_confirmation
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_id


@command("resetallwarns", allow_connected=True, chat_scope="group")
@anonadmin_checker(owner_only=True)
async def reset_all_warns(client, message):
    chat_id = effective_chat_id(message)
    user_id = actor_id(message)
    if not await has_chat_permission(client, chat_id, user_id, owner=True):
        return await message.reply(tr("resetallwarns.you_re_not_the_owner_of_this"))
    title = effective_chat(message).title or str(chat_id)
    await send_confirmation(
        message,
        tr("resetallwarns.are_you_sure_you_want_to_reset", title=html.escape(title)),
        "clear_warnings",
        {"chat_id": chat_id},
        [
            (
                "resetwarnsy",
                tr("resetallwarns.reset_all_warnings"),
                ButtonStyle.DANGER,
            ),
            ("resetwarnsn", tr("buttons.cancel"), ButtonStyle.DEFAULT),
        ],
        client=client,
    )


@callbackquery(filters=filters.regex("^resetwarns[yn]_"), access=CallbackAccess(public=True))
async def resetwarns_callback(client: Client, callback_query: CallbackQuery):
    data = await authorize_chat_confirmation(client, callback_query, "clear_warnings", owner=True)
    if data is None:
        return
    if callback_query.data.startswith("resetwarnsy_"):
        await reset_all_warns_db(data["chat_id"])
        text = tr("resetallwarns.reset_all_chat_warnings")
    else:
        text = tr("clone.cancelled")
    await callback_query.message.edit_text(text)
