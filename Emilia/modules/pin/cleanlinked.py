import html

from Emilia.custom_filter import command
from Emilia.database.pin import (
    antichannelpin_db,
    cleanlinked_db,
    get_antichannelpin,
    get_cleanlinked,
)
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_admins
from Emilia.utils.decorators import anonadmin_checker

CLEAN_LINKED_TRUE = ["on", "yes"]
CLEAN_LINKED_FALSE = ["off", "no"]


@command("cleanlinked", allow_connected=True, chat_scope="group")
@anonadmin_checker
async def cleanlinked(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await check_admins(message, privileges="can_delete_messages"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]
        if args in CLEAN_LINKED_TRUE:
            ANTICHANNEL_PIN = await get_antichannelpin(chat_id)
            if ANTICHANNEL_PIN:
                await message.reply(tr("cleanlinked.i_ve_disabled_antichannelpin_do_pininfo_to"))
                await antichannelpin_db(chat_id, False)

            await message.reply(
                tr(
                    "cleanlinked.enabled_linked_channel_post_deletion_messages_sent_from",
                    chat_title=html.escape(chat_title),
                )
            )
            await cleanlinked_db(chat_id, True)

        elif args in CLEAN_LINKED_FALSE:
            await message.reply(
                tr(
                    "cleanlinked.disabled_linked_channel_post_deletion",
                    chat_title=html.escape(chat_title),
                )
            )
            await cleanlinked_db(chat_id, False)

        else:
            await message.reply(tr("errors.invalid_toggle"))

    else:
        IS_CLEAN_LINK = await get_cleanlinked(chat_id)
        if IS_CLEAN_LINK:
            await message.reply(
                tr(
                    "cleanlinked.linked_channel_post_deletion_is_currently_enabled",
                    chat_title=html.escape(chat_title),
                )
            )

        else:
            await message.reply(
                tr(
                    "cleanlinked.linked_channel_post_deletion_is_currently_disabled",
                    chat_title=html.escape(chat_title),
                )
            )
