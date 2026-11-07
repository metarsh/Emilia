from functools import partial

from pyrogram import Client, filters
from pyrogram.types import Message

from Emilia.custom_filter import command, unified_wrapper
from Emilia.database.notes import GetNote, is_pnote_on, isNoteExist
from Emilia.locales import tr
from Emilia.modules.notes.private_notes import PrivateNoteButton
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.note_permissions import privateNote_and_admin_checker
from Emilia.utils.note_sender import exceNoteMessageSender
from Emilia.utils.saved_message import split_named_arguments


@command("get", allow_connected=True)
async def getNote(client, message):
    chat_id = effective_chat_id(message)
    try:
        note_name, _ = split_named_arguments(message.text or message.caption)
    except ValueError:
        return await message.reply(tr("get_note.you_need_to_give_the_note_a"))

    if not (await isNoteExist(chat_id, note_name)):
        return await message.reply(tr("get_note.note_not_found"))

    await send_note(client, message, note_name)


@Client.on_message(filters.regex(pattern=(r"^#[^\s]+")))
@partial(unified_wrapper, command_name="note", allow_connected=True)
async def regex_get_note(client, message):
    chat_id = effective_chat_id(message)
    if message.from_user and message.text is not None:
        note_name = message.text.split()[0].replace("#", "")
        if await isNoteExist(chat_id, note_name):
            await send_note(client, message, note_name)


async def send_note(client, message: Message, note_name: str):
    chat_id = effective_chat_id(message)
    content, text, data_type = await GetNote(chat_id, note_name)
    privateNote, allow = await privateNote_and_admin_checker(message, text, chat_id=chat_id)

    if allow:
        if privateNote is None:
            if await is_pnote_on(chat_id):
                await PrivateNoteButton(message, chat_id, note_name)
            else:
                await exceNoteMessageSender(client, message, note_name)

        elif privateNote is not None:
            if await is_pnote_on(chat_id):
                if privateNote:
                    await PrivateNoteButton(message, chat_id, note_name)
                else:
                    await exceNoteMessageSender(client, message, note_name)
            else:
                if privateNote:
                    await PrivateNoteButton(message, chat_id, note_name)
                else:
                    await exceNoteMessageSender(client, message, note_name)
