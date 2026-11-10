from pyrogram.errors import RPCError

from Emilia.application import LOGGER
from Emilia.custom_filter import command
from Emilia.database.welcome import SetWelcome
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.saved_message import SavedMessageType
from Emilia.utils.welcome_content import GetWelcomeMessage
from Emilia.utils.welcome_media import convert_welcome_media


@command("setwelcome", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def set_welcome(client, message):
    ChatID = effective_chat_id(message)

    if not await user_has_permission(message, chat_id=ChatID, privileges="can_change_info"):
        return

    CONTENT, TEXT, DATATYPE = GetWelcomeMessage(message, use_inline_text=True)
    if DATATYPE is None:
        return await message.reply(tr("set_welcome.you_need_to_give_the_welcome_message"))

    if DATATYPE != SavedMessageType.text.value and len(TEXT["text"]) > 1024:
        return await message.reply(tr("set_welcome.caption_too_long"))

    if DATATYPE in (SavedMessageType.sticker.value, SavedMessageType.video_note.value):
        try:
            CONTENT, DATATYPE = await convert_welcome_media(client, message, TEXT, DATATYPE)
        except (RPCError, OSError, TimeoutError, ValueError) as error:
            LOGGER.warning("Welcome media conversion failed: %s", type(error).__name__)
            return await message.reply(tr("set_welcome.media_conversion_failed"))

    await SetWelcome(ChatID, CONTENT, TEXT, DATATYPE)
    await message.reply(tr("set_welcome.the_new_welcome_message_has_been_saved"))
