from Emilia.custom_filter import command
from Emilia.database.locks import get_allowlist, rmallow_db
from Emilia.locales import tr
from Emilia.utils.allowlist import normalize_allowlist_url
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_user
from Emilia.utils.custom_emoji import (
    emojipack_token,
    is_emojipack_token,
    normalize_emojipack_name,
)
from Emilia.utils.decorators import anonadmin_checker


@command("rmallowlist", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def rmallow(client, message):
    chat_id = effective_chat_id(message)

    if not await check_user(message, privileges="can_change_info"):
        return

    if not (len(message.text.split()) >= 2):
        return await message.reply(tr("rmallowlist.you_haven_t_given_me_any_items"))

    RMALLOW_LIST = message.text.split()[1:]
    ALLOW_LIST = await get_allowlist(chat_id)

    CORRECT_LIST = []
    INCORRECT_LIST = []

    for rmallow in RMALLOW_LIST:
        if is_emojipack_token(rmallow):
            token = emojipack_token(normalize_emojipack_name(rmallow))
            if token:
                rmallow = token
        elif rmallow.startswith("-100") and rmallow[1:].isascii() and rmallow[1:].isdigit():
            rmallow = int(rmallow)
        elif not rmallow.startswith("@"):
            rmallow = normalize_allowlist_url(rmallow)
        if rmallow in ALLOW_LIST:
            CORRECT_LIST.append(rmallow)
        else:
            INCORRECT_LIST.append(rmallow)

    if len(INCORRECT_LIST) != 0:
        text = tr("rmallowlist.following_items_not_currently_allowlisted_can_t_removed")
        for item in INCORRECT_LIST:
            text += f"• `{item}`\n"

        return await message.reply(text)

    text = tr("rmallowlist.these_items_has_successfully_removed_from_allowlist")
    for item in CORRECT_LIST:
        await rmallow_db(chat_id, item)
        if len(CORRECT_LIST) == 1:
            text = tr("rmallowlist.removed_from_allowlist", item=item)
        else:
            text += f"• `{item}`\n"

    await message.reply(text)
