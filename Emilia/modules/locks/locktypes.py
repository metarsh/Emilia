from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.modules.locks import lock_map


@command("locktypes", disable=True)
async def locktypes(client, message):
    LOCKS_LIST = lock_map.LocksMap.list()

    text = tr("locktypes.available_locktypes")
    for lock in LOCKS_LIST:
        text += f"• {lock}\n"

    await message.reply(text)
