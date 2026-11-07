import html

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery

from Emilia.custom_filter import callbackquery, command
from Emilia.database.notes import ClearAllNotes, ClearNote, NoteList, isNoteExist
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_admins, has_chat_permission
from Emilia.utils.command_help import reply_usage
from Emilia.utils.confirmation import authorize_chat_confirmation, send_confirmation
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_id


@command("clear", allow_connected=True)
@anonadmin_checker
async def Clear_Note(client, message):
    chat_id = effective_chat_id(message)

    if not await check_admins(message, privileges=None):
        return

    command = message.text.split(" ")
    if len(command) == 1:
        await reply_usage(message, Clear_Note)
        return

    note_name = command[1].lower()

    if await isNoteExist(chat_id, note_name):
        await message.reply(tr("clear_note.ve_removed_note", note_name=note_name))
        await ClearNote(chat_id, note_name)

    else:
        await message.reply(tr("clear_note.you_haven_t_saved_a_note_with"))


@command("clearall", allow_connected=True)
@anonadmin_checker(owner_only=True)
async def ClearAll_Note(client, message):
    chat_id = effective_chat_id(message)
    user_id = actor_id(message)
    if not await has_chat_permission(client, chat_id, user_id, owner=True):
        return await message.reply(tr("clear_note.only_owner_can_execute_this_command"))
    title = effective_chat(message).title or str(chat_id)
    if not await NoteList(chat_id):
        return await message.reply(tr("clear_note.no_notes", title=html.escape(title)))
    await send_confirmation(
        message,
        tr("clear_note.are_you_sure_you_want_to_clear", title=html.escape(title)),
        "clear_notes",
        {"chat_id": chat_id},
        [
            (
                "clearallnotesy",
                tr("clear_note.delete_all_notes"),
                ButtonStyle.DANGER,
            ),
            ("clearallnotesn", tr("buttons.cancel"), ButtonStyle.DEFAULT),
        ],
        client=client,
    )


@callbackquery(filters=filters.regex("^clearallnotes[yn]_"), access=CallbackAccess(public=True))
async def ClearAllCallback(client: Client, callback_query: CallbackQuery):
    data = await authorize_chat_confirmation(client, callback_query, "clear_notes", owner=True)
    if data is None:
        return
    if callback_query.data.startswith("clearallnotesy_"):
        await ClearAllNotes(data["chat_id"])
        text = tr("clear_note.deleted_all_chat_notes")
    else:
        text = tr("clone.cancelled")
    await callback_query.message.edit_text(text)
