import html

from urlextract import URLExtract

from Emilia.custom_filter import command
from Emilia.database.locks import allowlist_db, get_allowlist
from Emilia.locales import tr
from Emilia.utils.allowlist import normalize_allowlist_url
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_user
from Emilia.utils.custom_emoji import (
    emojipack_token,
    extract_emojipack_tokens_from_command_target,
    is_emojipack_token,
    normalize_emojipack_name,
)
from Emilia.utils.decorators import anonadmin_checker

URL_EXTRACTOR = URLExtract()


@command("allowlist", chat_scope="group", allow_connected=True)
@anonadmin_checker
async def allowlist(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title or "local"

    if not await check_user(message, privileges="can_change_info"):
        return

    if len(message.text.split()) >= 2:
        ARG_LIST = message.text.split()[1:]
        INCORRECT_ITEMS = []
        CORRECT_ITEMS = []
        for arg in ARG_LIST:
            URLs_list = URL_EXTRACTOR.find_urls(arg)
            if is_emojipack_token(arg):
                normalized = normalize_emojipack_name(arg)
                if normalized:
                    token = emojipack_token(normalized)
                    if token:
                        CORRECT_ITEMS.append(token)
                else:
                    packs = await extract_emojipack_tokens_from_command_target(client, message)
                    if packs:
                        CORRECT_ITEMS.extend(sorted(packs))
                    else:
                        INCORRECT_ITEMS.append(arg)

            elif arg.startswith("-100"):
                if arg[1:].isascii() and arg[1:].isdigit():
                    CORRECT_ITEMS.append(int(arg))
                else:
                    INCORRECT_ITEMS.append(arg)

            elif arg.startswith("@"):
                CORRECT_ITEMS.append(arg)

            elif len(URLs_list) != 0:
                for url in URLs_list:
                    CORRECT_ITEMS.append(normalize_allowlist_url(url))

            else:
                INCORRECT_ITEMS.append(arg)

        if len(INCORRECT_ITEMS) != 0:
            text = tr("allowlist.have_rejected_these_args_added_allowlist_due_wrong")
            for item in INCORRECT_ITEMS:
                text += f"• {item}\n"

            return await message.reply(text)

        for item in CORRECT_ITEMS:
            await allowlist_db(chat_id, item)

        text = tr("allowlist.these_added_allowlist")
        for item in CORRECT_ITEMS:
            if len(CORRECT_ITEMS) == 1:
                text = tr("allowlist.added_allowlist", item=item)
            else:
                text += f"• {item}\n"

        await message.reply(text)

    else:
        ALLOW_LIST = await get_allowlist(chat_id)
        if len(ALLOW_LIST) != 0:
            text = tr("allowlist.following_items_allowlisted", chat_title=html.escape(chat_title))
            for item in ALLOW_LIST:
                text += f"• {item}\n"

            await message.reply(text)
        else:
            await message.reply(
                tr(
                    "allowlist.there_no_allowlisted_items",
                    there_no_allowlisted=html.escape(chat_title),
                )
            )
