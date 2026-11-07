from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.chat_status import check_admins
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.message_links import message_reference


@command("pin")
@anonadmin_checker
@log_to_channel
async def pin(client, message):
    chat_id = message.chat.id
    if not await check_admins(message, privileges="can_pin_messages"):
        return

    if not message.reply_to_message:
        return await reply_usage(message)

    pin_message_id = message.reply_to_message.id
    reference = message_reference(message.reply_to_message, "this message")

    if len(message.text.split()) == 1 or (
        len(message.text.split()) >= 2 and message.text.split()[1] in ("silent", "quiet")
    ):
        await client.pin_chat_message(
            chat_id=chat_id, message_id=pin_message_id, disable_notification=True
        )
        await message.reply(tr("pin.have_pinned_message", message_reference=reference))
        return "PIN", None, None

    elif len(message.text.split()) >= 2 and message.text.split()[1] in (
        "loud",
        "notify",
        "violent",
    ):
        await client.pin_chat_message(
            chat_id=chat_id, message_id=pin_message_id, disable_notification=False
        )
        await message.reply(
            tr("pin.have_pinned_message_notified_all_members", message_reference=reference)
        )
        return "LOUD_PIN", None, None

    elif len(message.text.split()) >= 2:
        await message.reply(
            tr("pin.not_recognised_valid_pin_option_please_use_one", option=message.text.split()[1])
        )
