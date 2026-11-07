import asyncio
import random
from traceback import format_exc as err

import tracemoepy
from aiohttp import ClientError
from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.errors import RPCError
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)
from redis.exceptions import RedisError
from tracemoepy.errors import APIError, InvalidPath, ServerError

from Emilia.application import db
from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.modules.anime.anilist import no_pic
from Emilia.utils.anime import (
    get_user_from_channel,
    media_to_image,
    rand_key,
    sender_id,
)
from Emilia.utils.anime_data import check_if_adult
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.errors import forward_traceback
from Emilia.utils.http import get_aiohttp_session
from Emilia.utils.menu_guard import CallbackAccess, remember_menu
from Emilia.utils.query_cache import QueryCache

SFW_GRPS = db["SFW_GROUPS"]

TRACE_MOE = QueryCache()


@command("anireverse", disable=True, group=954)
@anonadmin_checker(named=True, allow_channel=True)
async def reverse_search(client: Client, message: Message):
    """Reverse Search Anime Clips/Photos"""
    gid = message.chat.id
    user = sender_id(message)
    x = await message.reply_text(tr("tracemoepy.reverse_searching_the_given_media"))
    replied = message.reply_to_message
    if not replied:
        await reply_usage(message)
        await asyncio.sleep(5)
        await x.delete()
        return
    dls_loc = await media_to_image(client, x, replied)
    if dls_loc:
        # Use a shared session for the trace.moe request
        cs = await get_aiohttp_session()
        tracemoe = tracemoepy.AsyncTrace(session=cs)
        try:
            search = await tracemoe.search(dls_loc, upload_file=True)
        except ServerError:
            await x.edit_text(tr("tracemoepy.servererror_retrying"))
            try:
                search = await tracemoe.search(dls_loc, upload_file=True)
            except ServerError:
                await x.edit_text(tr("tracemoepy.couldnt_parse_results"))
                return
        except (APIError, InvalidPath, ClientError, OSError, ValueError):
            e = err()
            await x.edit_text(
                e.split("\n").pop(-2) + tr("tracemoepy.trying_again_in_2_3_minutes_might")
            )
            await forward_traceback("anime.media", e)
            return
        result = search["result"][0]
        caption_ = (
            f"**Title**: {result['anilist']['title']['english']}"
            + f" (`{result['anilist']['title']['native']}`)\n"
            + tr("tracemoepy.anilist_id", anime_id=result["anilist"]["id"])
            + f"**Similarity**: `{(str(result['similarity'] * 100))[:5]}`\n"
            + f"**Episode**: `{result['episode']}`"
        )
        preview = result["video"]
        dls_js = rand_key()
        TRACE_MOE[dls_js] = search
        button = []
        nsfw = False
        if await check_if_adult(int(result["anilist"]["id"])) and (
            await SFW_GRPS.find_one({"id": gid})
        ):
            msg = no_pic[random.randint(0, 4)]
            caption = tr("tracemoepy.the_results_seems_to_be_18_and")
            nsfw = True
        else:
            msg = preview
            caption = caption_
            button.append(
                [
                    InlineKeyboardButton(
                        tr("anime.more_info"),
                        url=f"https://anilist.co/anime/{result['anilist']['id']}",
                    )
                ]
            )
        button.append(
            [
                InlineKeyboardButton(
                    tr("buttons.next_arrow"), callback_data=f"tracech_1_{dls_js}_{user}"
                )
            ]
        )
        try:
            sent = await (message.reply_video if nsfw is False else message.reply_photo)(
                msg, caption=caption, reply_markup=InlineKeyboardMarkup(button)
            )
            await remember_menu(sent, user, client=client)
        except (RPCError, RedisError, OSError):
            e = err()
            await x.edit_text(
                e.split("\n").pop(-2) + tr("tracemoepy.trying_again_in_2_3_minutes_might")
            )
            await forward_traceback("anime.media", e)
            return
    else:
        await message.reply_text(tr("tracemoepy.couldn_t_parse_results"))
    await x.delete()


@callbackquery(
    filters=filters.regex(pattern="tracech_(.*)"),
    access=CallbackAccess(account_resolver=get_user_from_channel),
)
async def tracemoe_btn(client: Client, cq: CallbackQuery):
    kek, page, dls_loc, user = cq.data.split("_")
    try:
        TRACE_MOE[dls_loc]
    except KeyError:
        return await cq.answer(tr("anime.query_expired_create_new_one"), show_alert=True)
    search = TRACE_MOE[dls_loc]
    # Validate page bounds
    try:
        idx = int(page)
    except ValueError:
        return await cq.answer(tr("tracemoepy.invalid_page"), show_alert=True)
    if idx < 0 or idx >= len(search.get("result", [])):
        return await cq.answer(tr("tracemoepy.out_of_range"), show_alert=True)
    result = search["result"][idx]
    caption = (
        f"**Title**: {result['anilist']['title']['english']}"
        + f" (`{result['anilist']['title']['native']}`)\n"
        + tr("tracemoepy.anilist_id", anime_id=result["anilist"]["id"])
        + f"**Similarity**: `{(str(result['similarity'] * 100))[:5]}`\n"
        + f"**Episode**: `{result['episode']}`"
    )
    preview = result["video"]
    button = []
    if await check_if_adult(int(result["anilist"]["id"])) and (
        await SFW_GRPS.find_one({"id": cq.message.chat.id})
    ):
        msg = InputMediaPhoto(
            no_pic[random.randint(0, 4)],
            caption=tr("tracemoepy.the_results_seems_to_be_18_and"),
        )
    else:
        msg = InputMediaVideo(preview, caption=caption)
        button.append(
            [
                InlineKeyboardButton(
                    tr("anime.more_info"),
                    url=f"https://anilist.co/anime/{result['anilist']['id']}",
                )
            ]
        )
    if int(page) == 0:
        button.append(
            [
                InlineKeyboardButton(
                    tr("buttons.next_arrow"),
                    callback_data=f"tracech_{int(page) + 1}_{dls_loc}_{user}",
                )
            ]
        )
    elif int(page) == (len(search["result"]) - 1):
        button.append(
            [
                InlineKeyboardButton(
                    tr("buttons.back"),
                    callback_data=f"tracech_{int(page) - 1}_{dls_loc}_{user}",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        )
    else:
        button.append(
            [
                InlineKeyboardButton(
                    tr("buttons.back"),
                    callback_data=f"tracech_{int(page) - 1}_{dls_loc}_{user}",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    tr("buttons.next_arrow"),
                    callback_data=f"tracech_{int(page) + 1}_{dls_loc}_{user}",
                ),
            ]
        )
    await cq.edit_message_media(msg, reply_markup=InlineKeyboardMarkup(button))
