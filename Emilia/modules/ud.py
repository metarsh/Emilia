from pyrogram.errors import ChatWriteForbidden
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import get


async def get_ud_definition(text):
    url = "https://api.urbandictionary.com/v0/define"
    response = await get(url, params={"term": text})
    if response.status == 200:
        data = response.json()
        if "list" in data and data["list"]:
            return data["list"][0]
    return None


@command("ud", disable=True)
async def ud_command(client, message):
    words = (message.text or "").split(" ")

    if len(words) != 2:
        await reply_usage(message)
        return

    text = words[1]
    result = await get_ud_definition(text)

    if result:
        definition = result["definition"]
        example = result["example"]

        reply_text = (
            (f"**{text}**\n\n{definition}\n\n__{example}__").replace("[", "").replace("]", "")
        )
    else:
        reply_text = tr("findanime.no_results_found")

    search_url = f"https://www.google.com/search?q={text}"
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton(tr("ud.google_it"), url=search_url)]])

    try:
        await message.reply_text(reply_text, reply_markup=buttons)
    except ChatWriteForbidden:
        await message.reply_text(reply_text)


@command("define", disable=True)
async def define_command(client, message):
    user_input = (message.text or "").split(None, 1)[1]

    if not user_input:
        return await reply_usage(message)

    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{user_input}"
    response = await get(url)

    try:
        data = response.json()[0]
        meanings = data.get("meanings")
        if meanings:
            definition = meanings[0].get("definitions")[0].get("definition")
            if definition:
                await message.reply_text(
                    tr(
                        "ud.define_command_user_input_definition",
                        user_input=user_input.capitalize(),
                        definition=definition,
                    )
                )
                return

    except (TypeError, IndexError, KeyError):
        pass

    await message.reply_text(tr("ud.no_results_found"))
