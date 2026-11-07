import html

from Emilia.custom_filter import command
from Emilia.database.pin import (
    antichannelpin_db,
    get_antichannelpin,
    get_cleanlinked,
)
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_admins
from Emilia.utils.decorators import anonadmin_checker

ANTICHANNELPIN_TRUE = ["on", "yes"]
ANTICHANNELPIN_FALSE = ["off", "no"]


@command("antichannelpin", allow_connected=True, chat_scope="group")
@anonadmin_checker
async def antichannelpin(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await check_admins(message, privileges="can_pin_messages"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]
        if args in ANTICHANNELPIN_TRUE:
            CLEAN_LINKED = await get_cleanlinked(chat_id)
            if not CLEAN_LINKED:
                await message.reply(
                    tr("antichannelpin.enabled_anti_channel_pins_automatic_pins_from")
                )
                await antichannelpin_db(chat_id, True)

            else:
                await message.reply(
                    tr("antichannelpin.antichannelpin_and_cleanlinked_can_t_be_enabled")
                )

        elif args in ANTICHANNELPIN_FALSE:
            await message.reply(tr("antichannelpin.disabled_anti_channel_pins_automatic_pins_from"))
            await antichannelpin_db(chat_id, False)
        else:
            await message.reply(tr("errors.invalid_toggle"))

    else:
        IS_ANITICHANNEL = await get_antichannelpin(chat_id)
        if IS_ANITICHANNEL:
            await message.reply(
                tr(
                    "antichannelpin.anti_channel_pins_are_currently_enabled_in",
                    chat_title=html.escape(chat_title),
                )
            )

        else:
            await message.reply(
                tr(
                    "antichannelpin.anti_channel_pins_are_currently_disabled_in",
                    chat_title=html.escape(chat_title),
                )
            )
