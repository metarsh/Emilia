import asyncio
import random
import re
import time

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle, ChatAction, ChatType
from pyrogram.errors import RPCError, WebpageCurlFailed, WebpageMediaEmpty
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.utils.anime import (
    AUTH_USERS,
    PIC_LS,
    get_btns,
    query_identity,
    rand_key,
    sender_id,
)
from Emilia.utils.anime import get_user_from_channel as gcc
from Emilia.utils.anime_callbacks import list_callback, read_list_callback
from Emilia.utils.anime_data import (
    AIRING_DB,
    ANIME_DB,
    CHAR_DB,
    MANGA_DB,
    STUDIO_DB,
    anime_error,
    browse_,
    get_additional_info,
    get_airing,
    get_all_genres,
    get_all_tags,
    get_anilist,
    get_anime,
    get_character,
    get_featured_in_lists,
    get_manga,
    get_studio_animes,
    get_studios,
    get_top_animes,
    get_user,
    get_user_activity,
    get_user_favourites,
    toggle_favourites,
    update_anilist,
)
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import check_user
from Emilia.utils.client_context import bot_username
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.http import post
from Emilia.utils.menu_guard import CallbackAccess, remember_menu

SFW_GRPS = db["SFW_GROUPS"]
SG = db["SUBSPLEASE_GROUPS"]
MHD = db["MAL_HEADLINES_GROUPS"]


async def _settings_access(client, query, chat_id, *, privilege="can_change_info"):
    chat_id = int(chat_id)
    if chat_id >= 0 or (
        query.message.chat.type != ChatType.PRIVATE and query.message.chat.id != chat_id
    ):
        await query.answer(tr("anime.you_don_t_have_enough_permissions_to"), show_alert=True)
        return False
    return await CallbackAccess(chat_id=chat_id, privilege=privilege).allows(client, query)


failed_pic = "https://telegra.ph/file/09733b49f3a9d5b147d21.png"
no_pic = [
    "https://telegra.ph/file/0d2097f442e816ba3f946.jpg",
    "https://telegra.ph/file/5a152016056308ef63226.jpg",
    "https://telegra.ph/file/d2bf913b18688c59828e9.jpg",
    "https://telegra.ph/file/d53083ea69e84e3b54735.jpg",
    "https://telegra.ph/file/b5eb1e3606b7d2f1b491f.jpg",
]


@command("anime", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def anime_cmd(client: Client, message: Message):
    """Search Anime Info"""
    text = (message.text or message.caption or "").split(maxsplit=1)
    gid = message.chat.id
    try:
        await client.send_chat_action(gid, ChatAction.TYPING)
    except (RPCError, OSError):
        pass
    user, auser = await query_identity(message)
    if len(text) == 1:
        return await reply_usage(message)
    query = text[1]
    auth = False
    vars_ = {"search": query}
    if query.isdigit():
        vars_ = {"id": int(query)}
    if await AUTH_USERS.find_one({"id": auser}):
        auth = True
    result = await get_anime(
        vars_, user=auser, auth=auth, cid=gid if gid != user else None, client=client
    )
    if anime_error(result) is None:
        title_img, finals_ = result[0], result[1]
    else:
        k = await message.reply_text(anime_error(result))
        await asyncio.sleep(5)
        return await k.delete()
    buttons = await get_btns("ANIME", result=result, user=user, auth=auth, client=client)
    if await SFW_GRPS.find_one({"id": gid}) and result[2][-1] is True:
        await client.send_photo(
            gid,
            no_pic[random.randint(0, 4)],
            caption=tr("anime.this_anime_is_marked_18_and_not"),
        )
        return
    try:
        sent = await client.send_photo(gid, title_img, caption=finals_, reply_markup=buttons)
        await remember_menu(sent, user, client=client)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", title_img)
        sent = await client.send_photo(gid, failed_pic, caption=finals_, reply_markup=buttons)
        await remember_menu(sent, user, client=client)
    if title_img not in PIC_LS:
        PIC_LS.append(title_img)


@command("manga", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def manga_cmd(client: Client, message: Message):
    """Search Manga Info"""
    text = (message.text or message.caption or "").split(maxsplit=1)
    gid = message.chat.id
    try:
        await client.send_chat_action(gid, ChatAction.TYPING)
    except (RPCError, OSError):
        pass
    user, auser = await query_identity(message)
    if len(text) == 1:
        return await reply_usage(message)
    query = text[1]
    qdb = rand_key()
    MANGA_DB[qdb] = query
    auth = False
    if await AUTH_USERS.find_one({"id": auser}):
        auth = True
    result = await get_manga(
        qdb, 1, auth=auth, user=auser, cid=gid if gid != user else None, client=client
    )
    if anime_error(result) is not None:
        k = await message.reply_text(anime_error(result))
        await asyncio.sleep(5)
        return await k.delete()
    pic, finals_ = result[0], result[1][0]
    buttons = await get_btns(
        "MANGA", lsqry=qdb, lspage=1, user=user, result=result, auth=auth, client=client
    )
    if await SFW_GRPS.find_one({"id": gid}) and result[2][-1] is True:
        buttons = await get_btns(
            "MANGA",
            lsqry=qdb,
            lspage=1,
            user=user,
            result=result,
            auth=auth,
            sfw=True,
            client=client,
        )
        sent = await client.send_photo(
            gid,
            no_pic[random.randint(0, 4)],
            caption=tr("anime.this_manga_is_marked_18_and_not"),
            reply_markup=buttons,
        )
        await remember_menu(sent, user, client=client)
        return
    try:
        sent = await client.send_photo(gid, pic, caption=finals_, reply_markup=buttons)
        await remember_menu(sent, user, client=client)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        sent = await client.send_photo(gid, failed_pic, caption=finals_, reply_markup=buttons)
        await remember_menu(sent, user, client=client)
    if pic not in PIC_LS:
        PIC_LS.append(pic)


@command("character", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def character_cmd(client: Client, message: Message):
    """Get Info about a Character"""
    text = (message.text or message.caption or "").split(maxsplit=1)
    gid = message.chat.id
    try:
        await client.send_chat_action(gid, ChatAction.TYPING)
    except (RPCError, OSError):
        pass
    user, auser = await query_identity(message)
    if len(text) == 1:
        return await reply_usage(message)
    query = text[1]
    qdb = rand_key()
    CHAR_DB[qdb] = query
    auth = False
    if await AUTH_USERS.find_one({"id": auser}):
        auth = True
    result = await get_character(qdb, 1, auth=auth, user=auser)
    if anime_error(result) is not None:
        k = await message.reply_text(anime_error(result))
        await asyncio.sleep(5)
        return await k.delete()
    img = result[0]
    cap_text = result[1][0]
    buttons = await get_btns(
        "CHARACTER", user=user, lsqry=qdb, lspage=1, result=result, auth=auth, client=client
    )
    try:
        sent = await client.send_photo(gid, img, caption=cap_text, reply_markup=buttons)
        await remember_menu(sent, user, client=client)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", img)
        sent = await client.send_photo(gid, failed_pic, caption=cap_text, reply_markup=buttons)
        await remember_menu(sent, user, client=client)


@command("anilist", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def anilist_cmd(client: Client, message: Message):
    text = (message.text or message.caption or "").split(maxsplit=1)
    gid = message.chat.id
    user, auser = await query_identity(message)
    if len(text) == 1:
        return await reply_usage(message)
    query = text[1]
    qdb = rand_key()
    ANIME_DB[qdb] = query
    auth = False
    if await AUTH_USERS.find_one({"id": auser}):
        auth = True
    result = await get_anilist(
        qdb, 1, auth=auth, user=auser, cid=gid if gid != user else None, client=client
    )
    if anime_error(result) is not None:
        k = await message.reply_text(anime_error(result))
        await asyncio.sleep(5)
        return await k.delete()
    pic, msg = result[0], result[1][0]
    buttons = await get_btns(
        "ANIME", lsqry=qdb, lspage=1, result=result, user=user, auth=auth, client=client
    )
    if await SFW_GRPS.find_one({"id": gid}) and result[2][-1] is True:
        buttons = await get_btns(
            "ANIME",
            lsqry=qdb,
            lspage=1,
            result=result,
            user=user,
            auth=auth,
            sfw=True,
            client=client,
        )
        sent = await client.send_photo(
            gid,
            no_pic[random.randint(0, 4)],
            caption=tr("anime.this_anime_is_marked_18_and_not"),
            reply_markup=buttons,
        )
        await remember_menu(sent, user, client=client)
        return
    try:
        sent = await client.send_photo(gid, pic, caption=msg, reply_markup=buttons)
        await remember_menu(sent, user, client=client)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        sent = await client.send_photo(gid, failed_pic, caption=msg, reply_markup=buttons)
        await remember_menu(sent, user, client=client)
    if pic not in PIC_LS:
        PIC_LS.append(pic)


@command(["flex", "user"], disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def flex_cmd(client: Client, message: Message):
    query = (message.text or message.caption or "").split(maxsplit=1)
    gid = message.chat.id
    qry = None
    if "user" in query[0]:
        if not len(query) == 2:
            return await reply_usage(message)
        else:
            qry = {"search": query[1]}
    user, auser = await query_identity(message)
    if "user" not in query[0] and not (await AUTH_USERS.find_one({"id": auser})):
        return await message.reply_text(
            tr("anime.please_connect_your_account_first_to_use"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("anime.auth"),
                            url=f"https://t.me/{bot_username(client)}/?start=auth",
                        )
                    ]
                ]
            ),
        )
    result = await get_user(qry, query[0], auser, user)
    if anime_error(result) is not None:
        k = await message.reply_text(anime_error(result))
        await asyncio.sleep(5)
        return await k.delete()
    pic, msg, buttons = result
    try:
        sent = await client.send_photo(gid, pic, caption=msg, reply_markup=buttons)
        await remember_menu(sent, user, client=client)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        sent = await client.send_photo(gid, failed_pic, caption=msg, reply_markup=buttons)
        await remember_menu(sent, user, client=client)


@command("top", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def top_tags_cmd(client: Client, message: Message):
    query = (message.text or message.caption or "").split(maxsplit=1)
    gid = message.chat.id
    get_tag = "None"
    if len(query) == 2:
        get_tag = query[1]
    user = sender_id(message)
    result = await get_top_animes(get_tag, 1, user)
    if anime_error(result) is not None:
        k = await message.reply_text(anime_error(result))
        await asyncio.sleep(5)
        return await k.delete()
    if await SFW_GRPS.find_one({"id": gid}) and result[0][1] is True:
        return await message.reply_text(tr("anime.no_nsfw_stuff_allowed_in_this_group"))
    msg, buttons = result
    sent = await client.send_message(gid, msg[0], reply_markup=buttons if buttons != "" else None)
    await remember_menu(sent, user, client=client)


@command("studio", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def studio_cmd(client: Client, message: Message):
    text = (message.text or message.caption or "").split(maxsplit=1)
    gid = message.chat.id
    if len(text) == 1:
        return await reply_usage(message)
    query = text[1]
    qdb = rand_key()
    STUDIO_DB[qdb] = query
    auth = False
    user, auser = await query_identity(message)
    if await AUTH_USERS.find_one({"id": auser}):
        auth = True
    result = await get_studios(qdb, 1, user=auser, duser=user, auth=auth)
    if anime_error(result) is not None:
        x = await message.reply_text(tr("anime.no_results_found"))
        await asyncio.sleep(5)
        return await x.delete()
    msg, buttons = result[0], result[1]
    sent = await client.send_message(gid, msg, reply_markup=buttons if buttons != "" else None)
    await remember_menu(sent, user, client=client)


@command("airing", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def airing_cmd(client: Client, message: Message):
    """Get Airing Detail of Anime"""
    text = (message.text or message.caption or "").split(maxsplit=1)
    gid = message.chat.id
    if len(text) == 1:
        return await reply_usage(message)
    query = text[1]
    qdb = rand_key()
    AIRING_DB[qdb] = query
    auth = False
    user, auser = await query_identity(message)
    if await AUTH_USERS.find_one({"id": auser}):
        auth = True
    result = await get_airing(qdb, 1, auth=auth, user=auser)
    if anime_error(result) is not None:
        k = await message.reply_text(anime_error(result))
        await asyncio.sleep(5)
        return await k.delete()
    coverImg, out = result[0]
    btn = await get_btns(
        "AIRING", user=user, result=result, auth=auth, lsqry=qdb, lspage=1, client=client
    )
    if await SFW_GRPS.find_one({"id": gid}) and result[2][-1] is True:
        btn = await get_btns(
            "AIRING",
            user=user,
            result=result,
            auth=auth,
            lsqry=qdb,
            lspage=1,
            sfw=True,
            client=client,
        )
        sent = await client.send_photo(
            gid,
            no_pic[random.randint(0, 4)],
            caption=tr("anime.this_anime_is_marked_18_and_not"),
            reply_markup=btn,
        )
        await remember_menu(sent, user, client=client)
        return
    try:
        sent = await client.send_photo(gid, coverImg, caption=out, reply_markup=btn)
        await remember_menu(sent, user, client=client)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", coverImg)
        sent = await client.send_photo(gid, failed_pic, caption=out, reply_markup=btn)
        await remember_menu(sent, user, client=client)
    update = True
    for i in PIC_LS:
        if coverImg in i:
            update = False
            break
    if update:
        PIC_LS.append(coverImg)


@command("auth")
async def auth_link_cmd(client, message: Message):
    if message.chat.type == ChatType.PRIVATE:
        if not Config.ANILIST_CLIENT or not Config.ANILIST_SECRET:
            return await message.reply_text(tr("anime.authorization_not_configured"))
        text = tr("anime.authorization_pin")
        base = "https://anilist.co/api/v2/oauth/authorize?client_id="
        ac = Config.ANILIST_CLIENT
        aru = Config.ANILIST_REDIRECT_URL
        await message.reply_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=tr("anime.authorize"),
                            url=f"{base}{ac}&redirect_uri={aru}&response_type=code",
                        )
                    ]
                ]
            ),
        )
    else:
        await message.reply_text(
            tr("anime.go_to_bot_pm_to_authorize_yourself"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("anime.auth"),
                            url=f"https://t.me/{bot_username(client)}/?start=auth",
                        )
                    ]
                ]
            ),
        )


setting_text = tr("anime.allows_change_group_settings_nsfw_toggle_switches_filtering")


@command("anisettings", chat_scope="group_or_channel", allow_connected=True)
@anonadmin_checker
async def settings_cmd(client: Client, message: Message):
    cid = effective_chat_id(message)
    if not await check_user(message, privileges="can_change_info"):
        return
    sfw = tr("anime.nsfw_allowed")
    if await SFW_GRPS.find_one({"id": cid}):
        sfw = tr("anime.nsfw_not_allowed")
    sp = tr("anime.subsplease_updates_off")
    if await SG.find_one({"_id": cid}):
        sp = tr("anime.subsplease_updates")
    await message.reply_text(
        text=setting_text,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton(text=sfw, callback_data=f"settogl_sfw_{cid}")],
                [InlineKeyboardButton(text=sp, callback_data=f"settogl_sp_{cid}")],
                [
                    InlineKeyboardButton(
                        text=tr("anime.headlines"),
                        callback_data=f"headlines_call_{cid}",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text=tr("anime.change_ui"),
                        callback_data=f"cui_call_{cid}",
                    )
                ],
            ]
        ),
    )


@command("code", chat_scope="private")
async def man_code_cmd(client: Client, message: Message):
    text = message.text.split(maxsplit=1)
    if len(text) == 1:
        return await reply_usage(message)
    await code_cmd(text[1], message)


async def code_cmd(code: str, message: Message):
    if not message.from_user or message.chat.type != ChatType.PRIVATE:
        return await message.reply_text(tr("anime.send_this_cmd_in_pm"))
    if not Config.ANILIST_CLIENT or not Config.ANILIST_SECRET:
        return await message.reply_text(tr("anime.authorization_not_configured"))
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    json = {
        "grant_type": "authorization_code",
        "client_id": Config.ANILIST_CLIENT,
        "client_secret": Config.ANILIST_SECRET,
        "redirect_uri": Config.ANILIST_REDIRECT_URL,
        "code": code,
    }
    us_ = message.from_user.id
    if await AUTH_USERS.find_one({"id": us_}):
        return await message.reply_text(tr("anime.you_have_already_authorized_yourself_if_you"))
    response_obj = await post("https://anilist.co/api/v2/oauth/token", headers=headers, json=json)
    if response_obj.status != 200:
        await message.reply_text(
            tr("anime.please_retry_authorization_process_something_unexpected_happened")
        )
        return
    response = response_obj.json()
    token = response.get("access_token") if isinstance(response, dict) else None
    if isinstance(token, str) and token:
        await atomic_upsert(AUTH_USERS, {"id": us_}, {"$set": {"id": us_, "token": token}})
        await message.reply_text(tr("anime.authorization_successfull"))
    else:
        await message.reply_text(
            tr("anime.please_retry_authorization_process_something_unexpected_happened")
        )


@command(["ame", "activity"], disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def activity_cmd(client: Client, message: Message):
    user, auser = await query_identity(message)
    gid = message.chat.id
    if not (await AUTH_USERS.find_one({"id": auser})):
        return await message.reply_text(
            tr("anime.please_connect_your_account_first_to_use"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("anime.auth"),
                            url=f"https://t.me/{bot_username(client)}/?start=auth",
                        )
                    ]
                ]
            ),
        )
    result = await get_user(None, "flex", auser)
    if error := anime_error(result):
        return await message.reply_text(error)
    query = result[0].split("/").pop().split("?")[0]
    result = await get_user_activity(int(query), user=auser)
    pic, msg, kek = result
    btns = InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr("anime.profile"), url=f"https://anilist.co/user/{query}")]]
    )
    try:
        sent = await client.send_photo(gid, pic, caption=msg, reply_markup=btns)
        await remember_menu(sent, user, client=client)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        sent = await client.send_photo(gid, failed_pic, caption=msg, reply_markup=btns)
        await remember_menu(sent, user, client=client)


@command("favourites", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def favourites_cmd(client: Client, message: Message):
    user, auser = await query_identity(message)
    gid = message.chat.id
    if not (await AUTH_USERS.find_one({"id": auser})):
        return await message.reply_text(
            tr("anime.please_connect_your_account_first_to_use"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("anime.auth"),
                            url=f"https://t.me/{bot_username(client)}/?start=auth",
                        )
                    ]
                ]
            ),
        )
    result = await get_user(None, "flex", auser)
    if error := anime_error(result):
        return await message.reply_text(error)
    query = result[0].split("/").pop().split("?")[0]
    btn = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("anime.anime"),
                    callback_data=f"myfavqry_ANIME_{query}_1_no_{user}",
                ),
                InlineKeyboardButton(
                    tr("anime.character"),
                    callback_data=f"myfavqry_CHAR_{query}_1_no_{user}",
                ),
                InlineKeyboardButton(
                    tr("anime.manga_list_favourites_btn"),
                    callback_data=f"myfavqry_MANGA_{query}_1_no_{user}",
                ),
            ],
            [InlineKeyboardButton(tr("anime.profile"), url=f"https://anilist.co/user/{query}")],
        ]
    )
    try:
        sent = await client.send_photo(
            gid,
            result[0],
            caption=tr("anime.choose_one_of_the_below_options"),
            reply_markup=btn,
        )
        await remember_menu(sent, user, client=client)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", result[0])
        sent = await client.send_photo(
            gid,
            failed_pic,
            caption=tr("anime.choose_one_of_the_below_options"),
            reply_markup=btn,
        )
        await remember_menu(sent, user, client=client)


@command("logout")
async def logout_cmd(client: Client, message: Message):
    if message.chat.type == ChatType.PRIVATE:
        user = message.from_user.id
        if await AUTH_USERS.find_one({"id": user}):
            await AUTH_USERS.find_one_and_delete({"id": user})
            await message.reply_text(tr("anime.logged_out"))
        else:
            await message.reply_text(tr("anime.you_are_not_authorized_to_begin_with"))
    else:
        await message.reply_text(
            tr("anime.send_this_cmd_in_pm"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("anime.logout"),
                            url=f"https://t.me/{bot_username(client)}/?start=logout",
                        )
                    ]
                ]
            ),
        )


def _browse_keyboard(user: int, selected: str):
    categories = (
        ("trending", tr("anime.browse_trending")),
        ("popular", tr("anime.browse_popular")),
        ("upcoming", tr("anime.browse_upcoming")),
    )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"• {label} •" if category == selected else label,
                    callback_data=f"browse_{category}_{user}",
                )
                for category, label in categories
            ]
        ]
    )


@command("browse", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def browse_cmd(client: Client, message: Message):
    sent = await message.reply_text(
        await browse_("trending"), reply_markup=_browse_keyboard(sender_id(message), "trending")
    )
    await remember_menu(sent, sender_id(message), client=client)


@command(["getgenres", "gettags"], disable=True)
async def list_tags_genres_cmd(client, message: Message):
    gid = message.chat.id
    text = message.text or message.caption or ""
    if await SFW_GRPS.find_one({"id": gid}) and "nsfw" in text:
        return await message.reply_text(tr("anime.no_nsfw_allowed_here"))
    msg = (await get_all_tags(text)) if "gettags" in text.split()[0] else (await get_all_genres())
    await message.reply_text(msg)


@callbackquery(
    filters=filters.regex(pattern="page_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def page_btn(client: Client, cq: CallbackQuery):
    kek, media, query, page, auth, user = cq.data.split("_")
    user = int(user)
    gid = cq.message.chat.id
    if media == "ANIME":
        try:
            ANIME_DB[query]
        except KeyError:
            return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    if media == "MANGA":
        try:
            MANGA_DB[query]
        except KeyError:
            return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    if media == "CHARACTER":
        try:
            CHAR_DB[query]
        except KeyError:
            return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    if media == "AIRING":
        try:
            AIRING_DB[query]
        except KeyError:
            return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    authbool = bool(1) if auth == "True" else bool(0)
    if int(user) < 0:
        auser = await gcc(user, client=client)
    else:
        auser = user
    if media in ["ANIME", "MANGA"]:
        result = await (get_anilist if media == "ANIME" else get_manga)(
            query,
            int(page),
            auth=authbool,
            user=int(auser),
            cid=gid if gid != user else None,
        )
    else:
        result = await (get_character if media == "CHARACTER" else get_airing)(
            query, int(page), auth=authbool, user=int(auser)
        )
    if anime_error(result) is not None:
        await cq.answer(tr("anime.no_more_results_available"), show_alert=True)
        return
    pic, msg = result[0], result[1][0]
    if media == "AIRING":
        pic, msg = result[0][0], result[0][1]
    button = await get_btns(
        media, lsqry=query, lspage=int(page), result=result, user=user, auth=authbool, client=client
    )
    if await SFW_GRPS.find_one({"id": gid}) and media != "CHARACTER" and result[2][-1] is True:
        button = await get_btns(
            media,
            lsqry=query,
            lspage=int(page),
            result=result,
            user=user,
            auth=authbool,
            sfw=True,
            client=client,
        )
        await cq.edit_message_media(
            InputMediaPhoto(
                no_pic[random.randint(0, 4)],
                caption=tr("anime.this_material_is_marked_18_and_not"),
            ),
            reply_markup=button,
        )
        return
    try:
        await cq.edit_message_media(InputMediaPhoto(pic, caption=msg), reply_markup=button)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(InputMediaPhoto(failed_pic, caption=msg), reply_markup=button)
    await cq.answer()
    if media != "CHARACTER":
        if pic not in PIC_LS:
            PIC_LS.append(pic)


@callbackquery(
    filters=filters.regex(pattern="pgstudio_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def studio_pg_btn(client: Client, cq: CallbackQuery):
    kek, page, qry, auth, user = cq.data.split("_")
    authbool = bool(1) if auth == "True" else bool(0)
    try:
        STUDIO_DB[qry]
    except KeyError:
        return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    if int(user) < 0:
        auser = await gcc(user, client=client)
    else:
        auser = user
    result = await get_studios(qry, page=page, user=auser, duser=user, auth=authbool)
    if anime_error(result) is not None:
        return await cq.answer(tr("anime.no_more_results_available"), show_alert=True)
    msg, buttons = result[0], result[1]
    await cq.edit_message_text(msg, reply_markup=buttons)


@callbackquery(
    filters=filters.regex(pattern="stuani_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def studio_ani_btn(client: Client, cq: CallbackQuery):
    kek, page, id_, rp, qry, auth, user = cq.data.split("_")
    authbool = bool(1) if auth == "True" else bool(0)
    if int(user) < 0:
        auser = await gcc(user, client=client)
    else:
        auser = user
    result = await get_studio_animes(id_, page, qry, rp, auser, user, authbool)
    if anime_error(result) is not None:
        return await cq.answer(tr("anime.no_results_available"), show_alert=True)
    msg, buttons = result[0], result[1]
    await cq.edit_message_text(msg, reply_markup=buttons)


@callbackquery(
    filters=filters.regex(pattern="btn_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def anime_btn(client: Client, cq: CallbackQuery):
    await cq.answer()
    query = cq.data.split("_")
    idm = query[1]
    user = int(query.pop())
    if int(user) < 0:
        auser = await gcc(user, client=client)
    else:
        auser = user
    authbool = bool(1) if query[2] == "True" else bool(0)
    vars_ = {"id": int(idm)}
    cid = cq.message.chat.id
    result = await get_anime(
        vars_, auth=authbool, user=auser, cid=cid if cid != user else None, client=client
    )
    if error := anime_error(result):
        return await cq.edit_message_caption(error)
    pic, msg = result[0], result[1]
    btns = await get_btns("ANIME", result=result, user=user, auth=authbool, client=client)
    try:
        await cq.edit_message_media(InputMediaPhoto(pic, caption=msg), reply_markup=btns)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(InputMediaPhoto(failed_pic, caption=msg), reply_markup=btns)
    if pic not in PIC_LS:
        PIC_LS.append(pic)


@callbackquery(
    filters=filters.regex(pattern="topanimu_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def top_tags_btn(client: Client, cq: CallbackQuery):
    await cq.answer()
    kek, gnr, page, user = cq.data.split("_")
    result = await get_top_animes(gnr, page=page, user=user)
    if error := anime_error(result):
        return await cq.edit_message_text(error)
    msg, buttons = result[0][0], result[1]
    await cq.edit_message_text(msg, reply_markup=buttons)


@callbackquery(
    filters=filters.regex(pattern="^settogl_(call|sfw|sp)_-\\d+$"),
    access=CallbackAccess(public=True),
)
async def nsfw_toggle_btn(client: Client, cq: CallbackQuery):
    gid = int(cq.data.split("_").pop())
    if not await _settings_access(client, cq, gid):
        return
    query = cq.data.split("_")
    if await SFW_GRPS.find_one({"id": int(query[2])}):
        sfw = tr("anime.nsfw_not_allowed")
    else:
        sfw = tr("anime.nsfw_allowed")
    if await SG.find_one({"_id": int(query[2])}):
        sp = tr("anime.subsplease_updates")
    else:
        sp = tr("anime.subsplease_updates_off")
    if query[1] == "sfw":
        if await SFW_GRPS.find_one({"id": int(query[2])}):
            await SFW_GRPS.find_one_and_delete({"id": int(query[2])})
            sfw = tr("anime.nsfw_allowed")
        else:
            # Idempotent toggle using upsert
            await atomic_upsert(
                SFW_GRPS, {"id": int(query[2])}, {"$setOnInsert": {"id": int(query[2])}}
            )
            sfw = tr("anime.nsfw_not_allowed")
    if query[1] == "sp":
        if await SG.find_one({"_id": int(query[2])}):
            await SG.find_one_and_delete({"_id": int(query[2])})
            sp = tr("anime.subsplease_updates_off")
        else:
            # Idempotent toggle using upsert
            await atomic_upsert(
                SG, {"_id": int(query[2])}, {"$setOnInsert": {"_id": int(query[2])}}
            )
            sp = tr("anime.subsplease_updates")
    btns = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text=sfw, callback_data=f"settogl_sfw_{query[2]}")],
            [InlineKeyboardButton(text=sp, callback_data=f"settogl_sp_{query[2]}")],
            [
                InlineKeyboardButton(
                    text=tr("anime.headlines"),
                    callback_data=f"headlines_call_{query[2]}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=tr("anime.change_ui"),
                    callback_data=f"cui_call_{query[2]}",
                )
            ],
        ]
    )
    await cq.answer()
    if query[1] == "call":
        await cq.edit_message_text(text=setting_text, reply_markup=btns)


@callbackquery(
    filters=filters.regex(pattern="myacc_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def flex_btn(client: Client, cq: CallbackQuery):
    await cq.answer()
    query = cq.data.split("_")[1]
    user = cq.data.split("_").pop()
    if int(user) < 0:
        auser = await gcc(user, client=client)
    else:
        auser = user
    result = await get_user_activity(int(query), user=int(auser), duser=int(user))
    pic, msg, btns = result
    try:
        await cq.edit_message_media(InputMediaPhoto(pic, caption=msg), reply_markup=btns)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(InputMediaPhoto(failed_pic, caption=msg), reply_markup=btns)


@callbackquery(
    filters=filters.regex(pattern="myfavs_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def list_favourites_btn(client: Client, cq: CallbackQuery):
    await cq.answer()
    q = cq.data.split("_")
    btn = [
        [
            InlineKeyboardButton(
                tr("anime.anime"),
                callback_data=f"myfavqry_ANIME_{q[1]}_1_{q[2]}_{q[3]}",
            ),
            InlineKeyboardButton(
                tr("anime.character"),
                callback_data=f"myfavqry_CHAR_{q[1]}_1_{q[2]}_{q[3]}",
            ),
            InlineKeyboardButton(
                tr("anime.manga_list_favourites_btn"),
                callback_data=f"myfavqry_MANGA_{q[1]}_1_{q[2]}_{q[3]}",
            ),
        ]
    ]
    if q[2] == "yes":
        btn.append(
            [
                InlineKeyboardButton(
                    tr("buttons.back"),
                    callback_data=f"getusrbc_{q[3]}",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        )
    else:
        btn.append(
            [InlineKeyboardButton(tr("anime.profile"), url=f"https://anilist.co/user/{q[1]}")]
        )
    try:
        await cq.edit_message_media(
            InputMediaPhoto(
                f"https://img.anili.st/user/{q[1]}?a={time.time()}",
                caption=tr("anime.choose_one_of_the_below_options"),
            ),
            reply_markup=InlineKeyboardMarkup(btn),
        )
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", f"https://img.anili.st/user/{q[1]}?a={time.time()}")
        await cq.edit_message_media(
            InputMediaPhoto(failed_pic, caption=tr("anime.choose_one_of_the_below_options")),
            reply_markup=InlineKeyboardMarkup(btn),
        )


@callbackquery(
    filters=filters.regex(pattern="myfavqry_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def favourites_btn(client: Client, cq: CallbackQuery):
    await cq.answer()
    q = cq.data.split("_")
    if int(q[5]) < 0:
        auser = await gcc(q[5], client=client)
    else:
        auser = q[5]
    pic, msg, btns = await get_user_favourites(q[2], int(auser), q[1], q[3], q[4], duser=int(q[5]))
    try:
        await cq.edit_message_media(InputMediaPhoto(pic, caption=msg), reply_markup=btns)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(InputMediaPhoto(failed_pic, caption=msg), reply_markup=btns)


@callbackquery(
    filters=filters.regex(pattern="getusrbc_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def get_user_back_btn(client: Client, cq: CallbackQuery):
    await cq.answer()
    query = cq.data.split("_")[1]
    if int(query) < 0:
        auser = await gcc(query, client=client)
    else:
        auser = query
    result = await get_user(None, "flex", user=int(auser), display_user=query)
    if error := anime_error(result):
        return await cq.edit_message_caption(error)
    pic, msg, btns = result
    try:
        await cq.edit_message_media(InputMediaPhoto(pic, caption=msg), reply_markup=btns)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(InputMediaPhoto(failed_pic, caption=msg), reply_markup=btns)


@callbackquery(
    filters=filters.regex(pattern="fav_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def toggle_favourites_btn(client: Client, cq: CallbackQuery):
    query = cq.data.split("_")
    if query[1] == "ANIME" and len(query) > 4:
        try:
            ANIME_DB[query[3]]
        except KeyError:
            return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    if query[1] == "MANGA":
        try:
            MANGA_DB[query[3]]
        except KeyError:
            return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    if query[1] == "CHARACTER":
        try:
            CHAR_DB[query[3]]
        except KeyError:
            return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    if query[1] == "STUDIO":
        try:
            STUDIO_DB[query[3]]
        except KeyError:
            return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    idm = int(query[2])
    user = int(query.pop())
    if int(user) < 0:
        auser = await gcc(user, client=client)
    else:
        auser = user
    gid = cq.message.chat.id
    rslt = await toggle_favourites(id_=idm, media=query[1], user=auser)
    if rslt == "ok":
        await cq.answer(tr("anime.updated"), show_alert=True)
    else:
        return await cq.answer(tr("anime.failed_to_update"), show_alert=True)
    result = (
        (
            await get_anime(
                {"id": idm}, auth=True, user=auser, cid=gid if gid != user else None, client=client
            )
        )
        if query[1] == "ANIME" and len(query) == 3
        else (
            (
                await get_anilist(
                    query[3],
                    page=int(query[4]),
                    auth=True,
                    user=auser,
                    cid=gid if gid != user else None,
                    client=client,
                )
            )
            if query[1] == "ANIME" and len(query) != 3
            else (
                (
                    await get_manga(
                        query[3],
                        page=int(query[4]),
                        auth=True,
                        user=auser,
                        cid=gid if gid != user else None,
                        client=client,
                    )
                )
                if query[1] == "MANGA"
                else (
                    (await get_airing(query[3], auth=True, user=auser, ind=int(query[4])))
                    if query[1] == "AIRING"
                    else (
                        (await get_character(query[3], int(query[4]), auth=True, user=auser))
                        if query[1] == "CHARACTER"
                        else (
                            await get_studios(
                                query[3],
                                int(query[4]),
                                user=auser,
                                auth=True,
                                duser=user,
                            )
                        )
                    )
                )
            )
        )
    )
    if error := anime_error(result):
        return await cq.edit_message_caption(error)
    if query[1] == "STUDIO":
        return await cq.edit_message_text(result[0], reply_markup=result[1])
    pic, msg = (
        (result[0], result[1])
        if query[1] == "ANIME" and len(query) == 3
        else (result[0])
        if query[1] == "AIRING"
        else (result[0], result[1][0])
    )
    btns = await get_btns(
        query[1],
        result=result,
        user=user,
        auth=True,
        lsqry=query[3] if len(query) != 3 else None,
        lspage=int(query[4]) if len(query) != 3 else None,
        client=client,
    )
    try:
        await cq.edit_message_media(InputMediaPhoto(pic, caption=msg), reply_markup=btns)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(InputMediaPhoto(failed_pic, caption=msg), reply_markup=btns)


@callbackquery(pattern=r"^almenu:[A-Za-z0-9_-]{16}$", access=CallbackAccess(account_resolver=gcc))
@callbackquery(
    filters=filters.regex(pattern="(lsadd|lsupdt)_(.*)"),
    access=CallbackAccess(account_resolver=gcc),
)
async def list_update_anilist_btn(client: Client, cq: CallbackQuery):
    state = await read_list_callback(cq, client=client)
    if state is None:
        return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    await cq.answer()
    action = "lsas" if state["action"] == "lsadd" else "lsus"
    rows, row = [], []
    for status in ("COMPLETED", "CURRENT", "PLANNING", "DROPPED", "PAUSED", "REPEATING"):
        row.append(
            InlineKeyboardButton(
                status,
                callback_data=await list_callback(
                    state | {"action": action, "status": status},
                    client=client,
                    query=cq,
                ),
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if state["action"] == "lsupdt":
        rows.append(
            [
                InlineKeyboardButton(
                    tr("buttons.delete"),
                    style=ButtonStyle.DANGER,
                    callback_data=await list_callback(
                        state | {"action": "dlt", "status": None}, client=client, query=cq
                    ),
                )
            ]
        )
    await cq.edit_message_reply_markup(reply_markup=InlineKeyboardMarkup(rows))


@callbackquery(
    filters=filters.regex("^browse_(upcoming|trending|popular)_-?\\d+$"),
    access=CallbackAccess(account_resolver=gcc),
)
async def browse_btn(client: Client, cq: CallbackQuery):
    _, category, user = cq.data.split("_")
    await cq.edit_message_text(
        await browse_(category), reply_markup=_browse_keyboard(int(user), category)
    )
    await cq.answer()


@callbackquery(pattern=r"^alset:[A-Za-z0-9_-]{16}$", access=CallbackAccess(account_resolver=gcc))
@callbackquery(
    filters=filters.regex(pattern="(lsas|lsus|dlt)_(.*)"),
    access=CallbackAccess(account_resolver=gcc),
)
async def update_anilist_btn(client: Client, cq: CallbackQuery):
    state = await read_list_callback(cq, client=client)
    if state is None:
        return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    user = state["owner"]
    auser = await gcc(user, client=client) if user < 0 else user
    if not auser:
        return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    query, page, media = state["query"], state["page"] or 1, state["media"]
    databases = {"ANIME": ANIME_DB, "MANGA": MANGA_DB, "AIRING": AIRING_DB}
    if query is not None and query not in databases.get(media, {}):
        return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    result = await update_anilist(
        id_=state["media_id"],
        req=state["action"],
        status=state.get("status"),
        user=auser,
        eid=state["list_id"],
    )
    if result != "ok":
        return await cq.answer(
            tr("anime.something_unexpected_happened_and_operation_failed_successfully"),
            show_alert=True,
        )
    await cq.answer(tr("anime.updated"), show_alert=True)
    gid = cq.message.chat.id
    options = {"auth": True, "user": auser, "cid": gid if gid != user else None, "client": client}
    if media == "ANIME":
        result = (
            await get_anime({"id": state["media_id"]}, **options)
            if query is None
            else await get_anilist(query, page, **options)
        )
    elif media == "MANGA":
        result = await get_manga(query, page, **options)
    elif media == "AIRING":
        result = await get_airing(query, page, auth=True, user=auser)
    else:
        raise ValueError("Unsupported list media")
    if error := anime_error(result):
        return await cq.edit_message_caption(error)
    pic, msg = (
        result[0]
        if media == "AIRING"
        else (result[0], result[1] if query is None else result[1][0])
    )
    btns = await get_btns(
        media,
        result=result,
        user=user,
        auth=True,
        lsqry=query,
        lspage=page if query else None,
        client=client,
    )
    try:
        await cq.edit_message_media(InputMediaPhoto(pic, caption=msg), reply_markup=btns)
    except (WebpageMediaEmpty, WebpageCurlFailed):
        await cq.edit_message_media(InputMediaPhoto(failed_pic, caption=msg), reply_markup=btns)


@callbackquery(
    filters=filters.regex(pattern="(desc|ls|char)_(.*)"),
    access=CallbackAccess(account_resolver=gcc),
)
async def additional_info_btn(client: Client, cq: CallbackQuery):
    q = cq.data.split("_")
    kek, qry, ctgry = q[0], q[1], q[2]
    info = (
        "<b>Description</b>"
        if kek == "desc"
        else tr("anime.series_list")
        if kek == "ls"
        else tr("anime.characters_list")
    )
    page = 0
    lsqry = f"_{q[3]}" if len(q) > 6 else ""
    lspg = f"_{q[4]}" if len(q) > 6 else ""
    if kek == "char":
        page = q[6] if len(q) > 6 else q[4]
    rjsdata = await get_additional_info(qry, ctgry, kek, page=int(page))
    pic, result = rjsdata[0], rjsdata[1]
    button = []
    spoiler = False
    bot = bot_username(client)
    if result is None:
        await cq.answer(tr("anime.no_description_available"), show_alert=True)
        return
    if "~!" in result and "!~" in result:
        result = re.sub(r"~!.*!~", "[Spoiler]", result)
        spoiler = True
        button.append(
            [
                InlineKeyboardButton(
                    text=tr("anime.view_spoiler"),
                    url=f"https://t.me/{bot}/?start=des_{ctgry}_{qry}_desc",
                )
            ]
        )
    if len(result) > 1000:
        result = result[:940] + "..."
        if spoiler is False:
            result += tr("anime.more_info_click_below_given_button")
            button.append(
                [
                    InlineKeyboardButton(
                        text=tr("anime.more_info"),
                        url=f"https://t.me/{bot}/?start=des_{ctgry}_{qry}_{kek}",
                    )
                ]
            )
    add_ = ""
    user = q.pop()
    if kek == "char":
        btndata = rjsdata[2]
        if btndata["lastPage"] != 1:
            qs = q[5] if len(q) != 5 else q[3]
            pre = f"{kek}_{qry}_{ctgry}{lsqry}{lspg}_{qs}_{int(page) - 1}_{user}"
            nex = f"{kek}_{qry}_{ctgry}{lsqry}{lspg}_{qs}_{int(page) + 1}_{user}"
            if page == "1":
                button.append(
                    [InlineKeyboardButton(text=tr("buttons.next_arrow"), callback_data=nex)]
                )
            elif btndata["lastPage"] == int(page):
                button.append(
                    [InlineKeyboardButton(text=tr("buttons.previous_arrow"), callback_data=pre)]
                )
            else:
                button.append(
                    [
                        InlineKeyboardButton(text=tr("buttons.previous_arrow"), callback_data=pre),
                        InlineKeyboardButton(text=tr("buttons.next_arrow"), callback_data=nex),
                    ]
                )
        add_ = tr("anime.total_characters", total=btndata["total"])
    msg = f"{info}:\n\n{result + add_}"
    cbd = (
        f"btn_{qry}_{q[3]}_{user}"
        if len(q) <= 5
        else (
            f"page_ANIME{lsqry}{lspg}_{q[5]}_{user}"
            if ctgry == "ANI"
            else f"page_CHARACTER{lsqry}{lspg}_{q[5]}_{user}"
        )
    )
    button.append(
        [
            InlineKeyboardButton(
                text=tr("buttons.back"), callback_data=cbd, style=ButtonStyle.PRIMARY
            )
        ]
    )
    try:
        await cq.edit_message_media(
            InputMediaPhoto(pic, caption=msg), reply_markup=InlineKeyboardMarkup(button)
        )
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(
            InputMediaPhoto(failed_pic, caption=msg),
            reply_markup=InlineKeyboardMarkup(button),
        )
    await cq.answer()


@callbackquery(
    filters=filters.regex(pattern="lsc_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def featured_in_btn(client: Client, cq: CallbackQuery):
    kek, idm, qry, pg, auth, usr = cq.data.split("_")
    result = await get_featured_in_lists(int(idm), "ANI")
    req = "lscm"
    if result[0] is False:
        result = await get_featured_in_lists(int(idm), "MAN")
        req = None
        if result[0] is False:
            await cq.answer(tr("anime.no_data_available"), show_alert=True)
            return
    [msg, total], pic = result
    button = []
    totalpg, kek = divmod(total, 15)
    if kek != 0:
        totalpg + 1
    if total > 15:
        button.append(
            [
                InlineKeyboardButton(
                    text=tr("buttons.next_arrow"),
                    callback_data=f"lsca_{idm}_1_{qry}_{pg}_{auth}_{usr}",
                )
            ]
        )
    if req is not None:
        button.append(
            [
                InlineKeyboardButton(
                    text=tr("anime.manga"),
                    callback_data=f"lscm_{idm}_0_{qry}_{pg}_{auth}_{usr}",
                )
            ]
        )
    button.append(
        [
            InlineKeyboardButton(
                text=tr("buttons.back"),
                callback_data=f"page_CHARACTER_{qry}_{pg}_{auth}_{usr}",
                style=ButtonStyle.PRIMARY,
            )
        ]
    )
    try:
        await cq.edit_message_media(
            InputMediaPhoto(pic, caption=msg), reply_markup=InlineKeyboardMarkup(button)
        )
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(
            InputMediaPhoto(failed_pic, caption=msg),
            reply_markup=InlineKeyboardMarkup(button),
        )


@callbackquery(
    filters=filters.regex(pattern="lsc(a|m)_(.*)"), access=CallbackAccess(account_resolver=gcc)
)
async def featured_in_switch_btn(client: Client, cq: CallbackQuery):
    req, idm, reqpg, qry, pg, auth, user = cq.data.split("_")
    result = await get_featured_in_lists(
        int(idm), "MAN" if req == "lscm" else "ANI", page=int(reqpg)
    )
    reqb = "lsca" if req == "lscm" else "lscm"
    bt = "Anime" if req == "lscm" else "Manga"
    if result[0] is False:
        await cq.answer(tr("anime.no_data_available"), show_alert=True)
        return
    [msg, total], pic = result
    totalpg, kek = divmod(total, 15)
    if kek != 0:
        totalpg + 1
    button = []
    if total > 15:
        nex = f"{req}_{idm}_{int(reqpg) + 1}_{qry}_{pg}_{auth}_{user}"
        bac = f"{req}_{idm}_{int(reqpg) - 1}_{qry}_{pg}_{auth}_{user}"
        if int(reqpg) == 0:
            button.append([InlineKeyboardButton(text=tr("buttons.next_arrow"), callback_data=nex)])
        elif int(reqpg) == totalpg:
            button.append(
                [
                    InlineKeyboardButton(
                        text=tr("buttons.back"),
                        callback_data=bac,
                        style=ButtonStyle.PRIMARY,
                    )
                ]
            )
        else:
            button.append(
                [
                    InlineKeyboardButton(
                        text=tr("buttons.back"),
                        callback_data=bac,
                        style=ButtonStyle.PRIMARY,
                    ),
                    InlineKeyboardButton(text=tr("buttons.next_arrow"), callback_data=nex),
                ]
            )
    button.append(
        [
            InlineKeyboardButton(
                text=tr("admin.dare_dare", dare=bt),
                callback_data=f"{reqb}_{idm}_0_{qry}_{pg}_{auth}_{user}",
            )
        ]
    )
    button.append(
        [
            InlineKeyboardButton(
                text=tr("buttons.back"),
                callback_data=f"page_CHARACTER_{qry}_{pg}_{auth}_{user}",
                style=ButtonStyle.PRIMARY,
            )
        ]
    )
    try:
        await cq.edit_message_media(
            InputMediaPhoto(pic, caption=msg), reply_markup=InlineKeyboardMarkup(button)
        )
    except (WebpageMediaEmpty, WebpageCurlFailed):
        LOGGER.debug("Anime media URL: %s", pic)
        await cq.edit_message_media(
            InputMediaPhoto(failed_pic, caption=msg),
            reply_markup=InlineKeyboardMarkup(button),
        )


headlines_text = tr("anime.turn_myanimelist_option_get_news_feeds_from_myanimelist")


@callbackquery(
    filters=filters.regex(pattern="^headlines_(call|malhd|malhdpin)_-\\d+$"),
    access=CallbackAccess(public=True),
)
async def headlines_btn(client: Client, cq: CallbackQuery):
    qry = cq.data.split("_")[1]
    gid = int(cq.data.split("_")[2])
    privilege = "can_pin_messages" if qry == "malhdpin" else "can_change_info"
    if not await _settings_access(client, cq, gid, privilege=privilege):
        return
    maldata = await MHD.find_one({"_id": gid})
    malhd = tr("anime.myanimelist_off")
    malhdpin = tr("anime.auto_pin_off")
    malpin = None
    if maldata:
        malhd = tr("anime.myanimelist")
        try:
            malpin = maldata["pin"]
            malhdpin = tr("anime.auto_pin", malpin=malpin)
        except KeyError:
            pass

    data = maldata
    pin = malpin
    pin_msg = malhdpin
    collection = MHD
    src_status = malhd
    srcname = "MyAnimeList"

    if re.match(r"^malhd$", qry):
        if data:
            await collection.find_one_and_delete(data)
            src_status = f"{srcname}: OFF"
            pin_msg = tr("anime.auto_pin_off")
        else:
            await atomic_upsert(collection, {"_id": gid}, {"$setOnInsert": {"_id": gid}})
            src_status = f"{srcname}: ON"
            pin_msg = tr("anime.auto_pin_off")
    if re.match(r"^malhdpin$", qry):
        if data:
            if pin:
                switch = "ON" if pin == "OFF" else "OFF"
                await collection.find_one_and_update(
                    data, {"$set": {"pin": switch, "unpin": None}}, upsert=True
                )
                pin_msg = tr("anime.auto_pin", malpin=switch)
            else:
                await collection.find_one_and_update(data, {"$set": {"pin": "ON"}}, upsert=True)
                pin_msg = tr("anime.auto_pin_headlines_btn")
        else:
            await cq.answer(tr("anime.please_enable_first", srcname=srcname), show_alert=True)

    malhdpin = pin_msg
    malhd = src_status

    btn = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(text=malhd, callback_data=f"headlines_malhd_{gid}")],
            [
                InlineKeyboardButton(text=malhdpin, callback_data=f"headlines_malhdpin_{gid}"),
                InlineKeyboardButton(
                    text=tr("anime.auto_unpin_mal"),
                    callback_data=f"unpin_call_mal_{gid}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=tr("buttons.back"),
                    callback_data=f"settogl_call_{gid}",
                    style=ButtonStyle.PRIMARY,
                )
            ],
        ]
    )
    await cq.edit_message_text(headlines_text, reply_markup=btn)
    await cq.answer()


TIMES = {
    "1 day": 86400,
    "5 days": 432000,
    "1 week": 604800,
    "2 week": 1209600,
    "1 month": 2592000,
    "New Feed": 0,
    "OFF": None,
}


@callbackquery(
    filters=filters.regex(pattern="^unpin_(call|None|\\d+)_mal_-\\d+$"),
    access=CallbackAccess(public=True),
)
async def auto_unpin(client: Client, cq: CallbackQuery):
    qry = cq.data.split("_")[1]
    gid = int(cq.data.split("_")[3])
    if not await _settings_access(client, cq, gid, privilege="can_pin_messages"):
        return
    cancel = False
    srcname = "MyAnimeList"
    collection = MHD
    data = await collection.find_one({"_id": gid})
    if data:
        try:
            data["pin"]
            try:
                data["unpin"]
            except KeyError:
                pass
        except KeyError:
            cancel = True
    else:
        cancel = True
    if cancel:
        return await cq.answer(
            tr("anime.please_enable_auto_pin_option_them", srcname=srcname),
            show_alert=True,
        )
    setting = None
    if qry == "call":
        pass
    elif qry == "None":
        setting = {"unpin": None}
    elif qry.isdigit():
        if int(qry) not in TIMES.values():
            return await cq.answer(tr("anime.select_a_time_for_auto_unpin"), show_alert=True)
        if int(qry) == 0:
            setting = {"unpin": 0}
        else:
            now = round(time.time(), -2)
            setting = {"unpin": int(qry), "next_unpin": int(qry) + int(now)}
    if setting:
        await collection.find_one_and_update(data, {"$set": setting})
    btn = []
    row = []
    count = 0
    for i in TIMES.keys():
        count = count + 1
        if i == "New Feed":
            row.append(InlineKeyboardButton(text=i, callback_data=f"unpin_0_mal_{gid}"))
        else:
            if i == "OFF":
                row.append(InlineKeyboardButton(text=i, callback_data=f"unpin_None_mal_{gid}"))
            else:
                row.append(
                    InlineKeyboardButton(text=i, callback_data=f"unpin_{TIMES[i]}_mal_{gid}")
                )
        if count == 3:
            btn.append(row)
            row = []
            count = 0
    if row != []:
        btn.append(row)
    btn.append(
        [
            InlineKeyboardButton(
                text=tr("buttons.back"),
                callback_data=f"headlines_malhd_{gid}",
                style=ButtonStyle.PRIMARY,
            )
        ]
    )
    await cq.edit_message_text(
        tr("anime.select_a_time_for_auto_unpin"),
        reply_markup=InlineKeyboardMarkup(btn),
    )
    await cq.answer()


BULLETS = ["➤", "•", "⚬", "▲", "▸", "△", "⋟", "»", "None"]


@callbackquery(
    filters=filters.regex(pattern="^cui_[^_]+_-\\d+$"), access=CallbackAccess(public=True)
)
async def change_ui_btn(client: Client, cq: CallbackQuery):
    qry = cq.data.split("_")[1]
    gid = cq.data.split("_")[2]
    if not await _settings_access(client, cq, gid):
        return
    if qry not in {*BULLETS, "Caps", "UPPER", "call"}:
        return await cq.answer()
    await cq.answer()
    row, btn = [], []
    for i in BULLETS:
        row.append(InlineKeyboardButton(text=i, callback_data=f"cui_{i}_{gid}"))
        if len(row) == 3:
            btn.append(row)
            row = []
    btn.append(row)
    btn.append(
        [
            InlineKeyboardButton(text=tr("anime.caps"), callback_data=f"cui_Caps_{gid}"),
            InlineKeyboardButton(text=tr("anime.upper"), callback_data=f"cui_UPPER_{gid}"),
        ]
    )
    btn.append(
        [
            InlineKeyboardButton(
                text=tr("buttons.back"),
                callback_data=f"settogl_call_{gid}",
                style=ButtonStyle.PRIMARY,
            )
        ]
    )
    from Emilia.database.anime import update_ui

    updates = (
        {"cs": qry}
        if qry in ["Caps", "UPPER"]
        else {"bl": None if qry == "None" else qry}
        if qry != "call"
        else {}
    )
    data = await update_ui(gid, **updates)
    bl, cs = data["bl"], data["cs"]
    text = tr("anime.selected_bullet_group_selected_text_case_group", bullet=bl, text_case=cs)
    await cq.edit_message_text(text, reply_markup=InlineKeyboardMarkup(btn))
