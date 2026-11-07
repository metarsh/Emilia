from Emilia.custom_filter import command
from Emilia.database.filters import add_filter_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.get_data import get_text_reason
from Emilia.utils.message_content import formatted_text, replace_content, text_value
from Emilia.utils.saved_message import parse_saved_message


@command("filter", allow_connected=True)
@anonadmin_checker
async def filter(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    if message.reply_to_message and len(message.text.split()) < 2:
        await reply_usage(message, filter)
        return

    try:
        filter_name, _ = get_text_reason(message)
    except ValueError:
        await reply_usage(message, filter)
        return

    content, text, data_type = parse_saved_message(message)
    if data_type is None:
        await reply_usage(message, filter)
        return

    reply_to_sender = "{replytag}" in text_value(text)
    if reply_to_sender:
        text = replace_content(text, "{replytag}", "")
    text = formatted_text(text).record()
    accepted = await add_filter_db(
        chat_id,
        filter_name=filter_name,
        content=content,
        text=text,
        data_type=data_type,
        reply_to_sender=reply_to_sender,
    )
    if not accepted:
        await message.reply(tr("filter.you_can_t_have_more_than_69"))
        return
    await message.reply(tr("filter.saved_filter", filter_name=filter_name))
