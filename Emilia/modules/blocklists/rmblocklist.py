from Emilia.custom_filter import command
from Emilia.database.blocklists import get_blocklist, rmblocklist_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker


@command(
    ["rmblocklist", "rmblacklist", "unblocklist", "unblacklist"],
    chat_scope="group",
    allow_connected=True,
)
@anonadmin_checker
async def add_blocklist(client, message):
    chat_id = effective_chat_id(message)

    if not await is_user_admin(message):
        return

    if not (len(message.text.split()) >= 2):
        await reply_usage(message)
        return

    blocklist_word = " ".join(message.text.split()[1:])

    BLOCKLIST_DATA = await get_blocklist(chat_id)
    if BLOCKLIST_DATA is None or len(BLOCKLIST_DATA) == 0:
        return

    BLOCKLIST_ITMES = []
    for blocklist_array in BLOCKLIST_DATA:
        BLOCKLIST_ITMES.append(blocklist_array["blocklist_text"])

    if blocklist_word in BLOCKLIST_ITMES:
        await rmblocklist_db(chat_id, blocklist_word)
        await message.reply(
            tr("rmblocklist.will_no_longer_blocklist", blocklist_word=blocklist_word)
        )
    else:
        await message.reply(
            tr(
                "rmblocklist.hasn_t_blocklisted_couldn_t_stopped_use_blocklist",
                blocklist_word=blocklist_word,
            )
        )
