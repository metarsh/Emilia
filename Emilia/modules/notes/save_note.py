import html

from Emilia.custom_filter import command
from Emilia.database.notes import SaveNote
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_admins
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.note_content import GetNoteMessage
from Emilia.utils.saved_message import split_named_arguments


@command("save", allow_connected=True)
@anonadmin_checker
async def saveNote(client, message):
    chat_id = effective_chat_id(message)
    chat_title = html.escape(effective_chat(message).title or "local")

    if not await check_admins(message, privileges=None, silent=False):
        return

    try:
        NoteName, _ = split_named_arguments(message.text or message.caption)
    except ValueError:
        return await reply_usage(message, saveNote)

    Content, Text, DataType = GetNoteMessage(message)
    if DataType is None:
        return await reply_usage(message, saveNote)
    await SaveNote(chat_id, NoteName, Content, Text, DataType)
    await message.reply(tr("save_note.ve_saved_note", notename=NoteName, chat_title=chat_title))
