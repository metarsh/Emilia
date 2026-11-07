from Emilia.custom_filter import command
from Emilia.database.blocklists import add_blocklist_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_admins
from Emilia.utils.command_help import reply_usage
from Emilia.utils.custom_emoji import (
    emojipack_token,
    extract_emojipack_tokens_from_command_target,
    is_emojipack_token,
    normalize_emojipack_name,
)
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.get_data import get_text_reason


@command(["addblocklist", "addblacklist"], allow_connected=True, chat_scope="group")
@anonadmin_checker
async def add_blocklist(client, message):
    chat_id = effective_chat_id(message)

    if not await check_admins(message, privileges="can_restrict_members", chat_id=chat_id):
        return

    command = message.text.split(" ")
    if len(command) == 1:
        await reply_usage(message, add_blocklist)
        return

    try:
        text, reason = get_text_reason(message)
    except ValueError:
        return await reply_usage(message, add_blocklist)
    if is_emojipack_token(text):
        normalized = normalize_emojipack_name(text)
        tokens = set()
        if not normalized:
            tokens = await extract_emojipack_tokens_from_command_target(client, message)
            if not tokens:
                await message.reply(
                    tr("addblocklist.reply_to_a_message_containing_custom_emoji"),
                )
                return
        else:
            token = emojipack_token(normalized)
            if token:
                tokens.add(token)

        saved = []
        for token in sorted(tokens):
            if await add_blocklist_db(chat_id, token, reason):
                saved.append(token)
        if saved:
            await message.reply(
                tr("addblocklist.have_added_custom_emoji_pack_blocklist_filter").format(
                    "s" if len(saved) != 1 else "",
                    ", ".join(f"`{token}`" for token in saved),
                ),
            )
        if len(saved) < len(tokens):
            await message.reply(tr("addblocklist.you_can_t_have_more_than_69"))
        return

    if not await add_blocklist_db(chat_id, text, reason):
        await message.reply(tr("addblocklist.you_can_t_have_more_than_69"))
        return
    await message.reply(tr("addblocklist.have_added_blocklist_filter", have_added_blocklist=text))
