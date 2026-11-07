import html

from Emilia.custom_filter import command
from Emilia.database.notes import NoteList
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id


@command(["notes", "saved"], disable=True, allow_connected=True)
async def Notes(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title or "local"

    Notes_list = await NoteList(chat_id)

    NoteHeader = tr("notes.list_notes", chat_title=html.escape(chat_title))
    if len(Notes_list) != 0:
        for notes in Notes_list:
            NoteName = f" • `{notes}`\n"
            NoteHeader += NoteName
        await message.reply(
            tr("notes.can_retrieve_these_notes_using_get_notename_notename", noteheader=NoteHeader),
        )

    else:
        await message.reply(tr("notes.no_notes", chat_title=chat_title))
