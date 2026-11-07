import random
from html import escape

from aiohttp import ClientError
from pyrogram.enums import ParseMode
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto

from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.utils.http import get
from Emilia.utils.menu_guard import CallbackAccess


async def anime_quote(anime):
    try:
        r = await get(
            "https://api.animechan.io/v1/quotes/random",
            params={"anime": anime} if anime else {},
            timeout=10,
            retries=1,
            max_bytes=32768,
        )
        r.raise_for_status()
        data = r.json()["data"]
        result = data["content"], data["character"]["name"], data["anime"]["name"]
        if not all(isinstance(value, str) and value.strip() for value in result):
            raise ValueError("Invalid anime quote")
        return result
    except (ClientError, TimeoutError, ValueError, KeyError, TypeError):
        return None, None, None


@command("quote", disable=True)
async def quotes(client, message):
    parts = (message.text or "").split(None, 1)
    anim = parts[1] if len(parts) > 1 else None
    quote, character, anime = await anime_quote(anime=anim)
    if not quote:
        await message.reply_text(tr("animequote.no_quote_found"))
        return
    msg = tr(
        "animequote.quotes_quote_character_anime",
        quote=escape(quote),
        character=escape(character),
        anime=escape(anime),
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr("animequote.change"), callback_data="change_quote")]]
    )
    await message.reply_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@callbackquery(pattern=r"change_.*", access=CallbackAccess(public=True))
@callbackquery(pattern=r"quote_.*", access=CallbackAccess(public=True))
async def change_quote(client, query):
    await query.answer()
    quote, character, anime = await anime_quote(anime=None)
    if not quote:
        return
    msg = tr(
        "animequote.quotes_quote_character_anime",
        quote=escape(quote),
        character=escape(character),
        anime=escape(anime),
    )
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr("animequote.change"), callback_data="quote_change")]]
    )
    await query.edit_message_text(msg, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@command("animequotes", disable=True)
async def animequotes(client, message):
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr("animequote.change"), callback_data="changek_quote")]]
    )
    await client.send_photo(message.chat.id, random.choice(QUOTES_IMG), reply_markup=keyboard)


@callbackquery(pattern=r"changek_.*", access=CallbackAccess(public=True))
@callbackquery(pattern=r"quotek_.*", access=CallbackAccess(public=True))
async def changek_quote(client, query):
    await query.answer()
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr("animequote.change"), callback_data="quotek_change")]]
    )
    # editing media requires edit_message_media in pyrogram
    await query.edit_message_media(
        InputMediaPhoto(random.choice(QUOTES_IMG)), reply_markup=keyboard
    )


QUOTES_IMG = (
    "https://i.imgur.com/Iub4RYj.jpg",
    "https://i.imgur.com/uvNMdIl.jpg",
    "https://i.imgur.com/YOBOntg.jpg",
    "https://i.imgur.com/fFpO2ZQ.jpg",
    "https://i.imgur.com/f0xZceK.jpg",
    "https://i.imgur.com/RlVcCip.jpg",
    "https://i.imgur.com/CjpqLRF.jpg",
    "https://i.imgur.com/8BHZDk6.jpg",
    "https://i.imgur.com/8bHeMgy.jpg",
    "https://i.imgur.com/5K3lMvr.jpg",
    "https://i.imgur.com/NTzw4RN.jpg",
    "https://i.imgur.com/wJxryAn.jpg",
    "https://i.imgur.com/9L0DWzC.jpg",
    "https://i.imgur.com/sBe8TTs.jpg",
    "https://i.imgur.com/1Au8gdf.jpg",
    "https://i.imgur.com/28hFQeU.jpg",
    "https://i.imgur.com/Qvc03JY.jpg",
    "https://i.imgur.com/gSX6Xlf.jpg",
    "https://i.imgur.com/iP26Hwa.jpg",
    "https://i.imgur.com/uSsJoX8.jpg",
    "https://i.imgur.com/OvX3oHB.jpg",
    "https://i.imgur.com/JMWuksm.jpg",
    "https://i.imgur.com/lhM3fib.jpg",
    "https://i.imgur.com/64IYKkw.jpg",
    "https://i.imgur.com/nMbyA3J.jpg",
    "https://i.imgur.com/7KFQhY3.jpg",
    "https://i.imgur.com/mlKb7zt.jpg",
    "https://i.imgur.com/JCQGJVw.jpg",
    "https://i.imgur.com/hSFYDEz.jpg",
    "https://i.imgur.com/PQRjAgl.jpg",
    "https://i.imgur.com/ot9624U.jpg",
    "https://i.imgur.com/iXmqN9y.jpg",
    "https://i.imgur.com/RhNBeGr.jpg",
    "https://i.imgur.com/tcMVNa8.jpg",
    "https://i.imgur.com/LrVg810.jpg",
    "https://i.imgur.com/TcWfQlz.jpg",
    "https://i.imgur.com/muAUdvJ.jpg",
    "https://i.imgur.com/AtC7ZRV.jpg",
    "https://i.imgur.com/sCObQCQ.jpg",
    "https://i.imgur.com/AJFDI1r.jpg",
    "https://i.imgur.com/TCgmRrH.jpg",
    "https://i.imgur.com/LMdmhJU.jpg",
    "https://i.imgur.com/eyyax0N.jpg",
    "https://i.imgur.com/YtYxV66.jpg",
    "https://i.imgur.com/292w4ye.jpg",
    "https://i.imgur.com/6Fm1vdw.jpg",
    "https://i.imgur.com/2vnBOZd.jpg",
    "https://i.imgur.com/j5hI9Eb.jpg",
    "https://i.imgur.com/cAv7pJB.jpg",
    "https://i.imgur.com/jvI7Vil.jpg",
    "https://i.imgur.com/fANpjsg.jpg",
    "https://i.imgur.com/5o1SJyo.jpg",
    "https://i.imgur.com/dSVxmh8.jpg",
    "https://i.imgur.com/02dXlAD.jpg",
    "https://i.imgur.com/htvIoGY.jpg",
    "https://i.imgur.com/hy6BXOj.jpg",
    "https://i.imgur.com/OuwzNYu.jpg",
    "https://i.imgur.com/L8vwvc2.jpg",
    "https://i.imgur.com/3VMVF9y.jpg",
    "https://i.imgur.com/yzjq2n2.jpg",
    "https://i.imgur.com/0qK7TAN.jpg",
    "https://i.imgur.com/zvcxSOX.jpg",
    "https://i.imgur.com/FO7bApW.jpg",
    "https://i.imgur.com/KK06gwg.jpg",
    "https://i.imgur.com/6lG4tsO.jpg",
)
