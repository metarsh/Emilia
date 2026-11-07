from pyrogram import Client
from pyrogram.types import Message, MessageReactionUpdated

from Emilia.utils.reaction_updates import _handle_guest_message, _handle_message_reaction
from Emilia.utils.tg_safe import flood_safe


@Client.on_message_reaction(group=4)
async def moderate_reaction(client: Client, update: MessageReactionUpdated):
    await flood_safe(lambda: _handle_message_reaction(client, update))


@Client.on_guest_message(group=4)
async def moderate_guest_message(client: Client, message: Message):
    await flood_safe(lambda: _handle_guest_message(client, message))
