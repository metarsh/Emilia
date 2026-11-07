from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.chat_status import check_admins
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.message_links import message_reference


@command("unpin")
@anonadmin_checker
async def unpin(client, message):
    chat_id = message.chat.id
    if not await check_admins(message, privileges="can_pin_messages"):
        return

    if message.reply_to_message:
        pinned_message_id = message.reply_to_message.id
        reference = message_reference(message.reply_to_message, "here")
        await client.unpin_chat_message(chat_id=chat_id, message_id=pinned_message_id)
        await message.reply(tr("unpin.unpinned_message", message_reference=reference))

    else:
        chat_data = await client.get_chat(chat_id=chat_id)
        if chat_data.pinned_message:
            pinned_message_id = chat_data.pinned_message.id
            await client.unpin_chat_message(chat_id=chat_id, message_id=pinned_message_id)
            await message.reply(tr("unpin.unpinned_the_last_pinned_message"))
        else:
            await message.reply(tr("unpin.there_are_no_pinned_messages_what_are"))
