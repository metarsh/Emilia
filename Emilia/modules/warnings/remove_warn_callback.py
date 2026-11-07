from Emilia.custom_filter import callbackquery
from Emilia.database.warnings import remove_warn
from Emilia.locales import tr
from Emilia.utils.confirmation import authorize_chat_confirmation
from Emilia.utils.menu_guard import CallbackAccess


@callbackquery(pattern=r"^warnrm_[A-Za-z0-9_-]{16}$", group=1, access=CallbackAccess(public=True))
async def warn_remove_callback(client, query):
    data = await authorize_chat_confirmation(
        client, query, "remove_warn", privilege="can_restrict_members"
    )
    if data is None:
        return
    if not await remove_warn(data["chat_id"], data["user_id"], data["warning_id"]):
        return await query.answer(tr("custom_filter.this_button_has_expired"), show_alert=True)
    user = await client.get_users(data["user_id"])
    await query.answer()
    await query.message.edit_text(
        tr(
            "remove_warn_callback.admin_has_removed_s_warning",
            admin_mention=query.from_user.mention,
            user_mention=user.mention,
        )
    )
