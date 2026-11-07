import random

from Emilia.custom_filter import command
from Emilia.utils.http import get

MemesReddit = [
    "Animemes",
    "lostpause",
    "LoliMemes",
    "cleananimemes",
    "animememes",
    "goodanimemes",
    "AnimeFunny",
    "dankmemes",
    "teenagers",
    "shitposting",
    "Hornyjail",
    "wholesomememes",
    "cursedcomments",
]


@command("memes", disable=True)
async def memes(client, message):
    memereddit = random.choice(MemesReddit)
    meme_link = f"https://meme-api.com/gimme/{memereddit}"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("dank", disable=True)
async def dank(client, message):
    meme_link = "https://meme-api.com/gimme/dankmemes"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("lolimeme", disable=True)
async def lolimeme(client, message):
    meme_link = "https://meme-api.com/gimme/LoliMemes"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("hornyjail", disable=True)
async def hornyjail(client, message):
    meme_link = "https://meme-api.com/gimme/Hornyjail"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("wmeme", disable=True)
async def wmeme(client, message):
    meme_link = "https://meme-api.com/gimme/wholesomememes"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("pewds", disable=True)
async def pewds(client, message):
    meme_link = "https://meme-api.com/gimme/PewdiepieSubmissions"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("hmeme", disable=True)
async def hmeme(client, message):
    meme_link = "https://meme-api.com/gimme/hornyresistance"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("teen", disable=True)
async def teen(client, message):
    meme_link = "https://meme-api.com/gimme/teenagers"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("fbi", disable=True)
async def fbi(client, message):
    meme_link = "https://meme-api.com/gimme/FBI_Memes"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("shitposting", disable=True)
async def shitposting(client, message):
    meme_link = "https://meme-api.com/gimme/shitposting"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])


@command("cursed", disable=True)
async def cursed(client, message):
    meme_link = "https://meme-api.com/gimme/cursedcomments"
    q = await get(meme_link)
    q.raise_for_status()
    q_json = q.json()
    await message.reply_photo(q_json["url"], caption=q_json["title"])
