from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.http import get


async def fetch_question(url):
    r = await get(url)
    try:
        r.raise_for_status()
        data = r.json()
    except ValueError:
        return None
    question = data.get("question") if isinstance(data, dict) else None
    return question if isinstance(question, str) else None


async def get_dare_question():
    return await fetch_question("https://api.truthordarebot.xyz/v1/dare")


async def get_truth_question():
    return await fetch_question("https://api.truthordarebot.xyz/v1/truth")


@command("dare", disable=True)
async def dare(client, event):
    dare = await get_dare_question()
    if dare:
        await event.reply(tr("admin.dare_dare", dare=dare))


@command("truth", disable=True)
async def truth(client, event):
    truth = await get_truth_question()
    if truth:
        await event.reply(tr("admin.dare_dare", dare=truth))
