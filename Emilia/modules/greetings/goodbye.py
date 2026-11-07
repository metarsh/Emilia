from pyrogram.types import InlineKeyboardMarkup

from Emilia.custom_filter import command
from Emilia.database.welcome import (
    DEFAUT_GOODBYE,
    GetCleanService,
    GetGoobye,
    GetGoodbyemessageOnOff,
    SetGoodbyeMessageOnOff,
    isGoodbye,
)
from Emilia.locales import tr
from Emilia.utils.button_gen import button_markdown_parser
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import user_has_permission
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.welcome_sender import SendWelcomeMessage

GOODBYE_TRUE = ["on", "yes"]
GOODBYE_FALSE = ["off", "no"]


@command("goodbye", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def Welcome(client, message):
    chat_id = effective_chat_id(message)

    if not await user_has_permission(message, chat_id=chat_id, privileges="can_change_info"):
        return

    command = message.text.split(" ")
    if not (len(command) == 1):
        GetWelcomeArg = command[1]
        if GetWelcomeArg in GOODBYE_TRUE:
            await SetGoodbyeMessageOnOff(chat_id, goodbye_message=True)
            await message.reply(tr("goodbye.i_ll_be_saying_goodbye_to_any"))

        elif GetWelcomeArg in GOODBYE_FALSE:
            await SetGoodbyeMessageOnOff(chat_id, goodbye_message=False)
            await message.reply(tr("goodbye.i_ll_stay_quiet_when_people_leave"))

        else:
            await message.reply(tr("errors.invalid_toggle"))

    elif len(command) == 1:
        if await GetGoodbyemessageOnOff(chat_id):
            GoodByeMessage = "true"
        else:
            GoodByeMessage = "false"

        if await GetCleanService(chat_id):
            CleanService = "true"
        else:
            CleanService = "false"

        GOODBYE_MESSAGE = tr(
            "goodbye.am_currently_saying_goodbye_users_am_currently_deleting",
            goodbyemessage=GoodByeMessage,
            cleanservice=CleanService,
        )

        GoodByeSentMessage = await message.reply(GOODBYE_MESSAGE)

        if await isGoodbye(chat_id):
            Content, Text, DataType = await GetGoobye(chat_id)
            Text, buttons = button_markdown_parser(Text)

            reply_markup = None
            if len(buttons) > 0:
                reply_markup = InlineKeyboardMarkup(buttons)
            GoodByeSentMessage = await SendWelcomeMessage(
                client,
                message,
                None,
                Content,
                Text,
                DataType,
                reply_markup=reply_markup,
            )
        else:
            await GoodByeSentMessage.reply(DEFAUT_GOODBYE)
