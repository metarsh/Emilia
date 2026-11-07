from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.locales import tr
from Emilia.utils.client_context import bot_username
from Emilia.utils.note_sender import exceNoteMessageSender


async def note_redirect(client, message):
    chat_id = int(message.text.split()[1].split("_")[1])
    note_name = message.text.split()[1].split("_", 2)[2]
    await exceNoteMessageSender(client, message, note_name, from_chat_id=chat_id)


async def PrivateNoteButton(message, chat_id, NoteName):
    PrivateNoteButton = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text=tr("private_notes.click_me"),
                    url=f"https://t.me/{bot_username(message._client)}?start=note_{chat_id}_{NoteName}",
                )
            ]
        ]
    )
    await message.reply(
        text=tr("private_notes.tap_here_view_private_chat", notename=NoteName),
        reply_markup=PrivateNoteButton,
    )
