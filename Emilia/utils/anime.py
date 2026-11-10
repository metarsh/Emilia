import asyncio
import os
import time
from collections import deque
from datetime import datetime
from os.path import basename
from uuid import uuid4

from pymongo.errors import PyMongoError
from pyrogram import Client
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.locales import tr
from Emilia.services.scheduler import ManagedScheduler
from Emilia.utils.anime_callbacks import list_callback
from Emilia.utils.chat_status import has_chat_permission
from Emilia.utils.http import post
from Emilia.utils.message_actor import actor_id, actor_user
from Emilia.utils.process import run_process

AUTH_USERS = db["AUTH_USERS"]
PIC_DB = db["PIC_DB"]
CC = db["CONNECTED_CHANNELS"]


def sender_id(message: Message) -> int:
    return actor_id(message) or message.chat.id


async def query_identity(message: Message) -> tuple[int, int]:
    owner = sender_id(message)
    account = (
        await get_user_from_channel(owner, client=message._client)
        if actor_user(message) is None
        else None
    )
    return owner, account or owner


def rand_key():
    return str(uuid4())[:8]


async def media_to_image(client: Client, x: Message, replied: Message):
    if not (replied.photo or replied.sticker or replied.animation or replied.video):
        await x.edit_text(tr("anime.media_type_is_invalid"))
        await asyncio.sleep(5)
        await x.delete()
        return
    media = replied.photo or replied.sticker or replied.animation or replied.video
    if not os.path.isdir(Config.DOWN_PATH):
        os.makedirs(Config.DOWN_PATH)
    dls = await client.download_media(
        media,
        file_name=Config.DOWN_PATH + rand_key(),
    )
    dls_loc = os.path.join(Config.DOWN_PATH, os.path.basename(dls))
    if replied.sticker and replied.sticker.file_name.endswith(".tgs"):
        png_file = os.path.join(Config.DOWN_PATH, f"{rand_key()}.png")
        result = await run_process(
            "lottie_convert.py", "--frame", "0", "-if", "lottie", "-of", "png", dls_loc, png_file
        )
        stdout, stderr = result.stdout, result.stderr
        os.remove(dls_loc)
        if not os.path.lexists(png_file):
            await x.edit_text(tr("anime.this_sticker_is_gey_task_failed_successfully"))
            await asyncio.sleep(5)
            await x.delete()
            raise RuntimeError(stdout + stderr)
        dls_loc = png_file
    elif replied.sticker and replied.sticker.file_name.endswith(".webp"):
        stkr_file = os.path.join(Config.DOWN_PATH, f"{rand_key()}.png")
        os.rename(dls_loc, stkr_file)
        if not os.path.lexists(stkr_file):
            await x.edit_text(tr("anime.sticker_not_found"))
            await asyncio.sleep(5)
            await x.delete()
            return
        dls_loc = stkr_file
    elif replied.animation or replied.video:
        await x.edit_text(tr("anime.converting_media_to_image"))
        jpg_file = os.path.join(Config.DOWN_PATH, f"{rand_key()}.jpg")
        await take_screen_shot(dls_loc, 0, jpg_file)
        os.remove(dls_loc)
        if not os.path.lexists(jpg_file):
            await x.edit_text(tr("anime.this_gif_is_gey_task_failed_successfully"))
            await asyncio.sleep(5)
            await x.delete()
            return
        dls_loc = jpg_file
    return dls_loc


async def take_screen_shot(video_file: str, duration: int, path: str = "") -> str | None:
    """take a screenshot"""
    LOGGER.info(
        "[[[Extracting a frame from %s ||| Video duration => %s]]]",
        video_file,
        duration,
    )
    thumb_image_path = path or os.path.join(Config.DOWN_PATH, f"{basename(video_file)}.jpg")
    result = await run_process(
        "ffmpeg", "-ss", str(duration), "-i", video_file, "-vframes", "1", thumb_image_path
    )
    err = result.stderr
    if err:
        LOGGER.error(err)
    return thumb_image_path if os.path.exists(thumb_image_path) else None


##################################################################


async def get_user_from_channel(cid, *, client):
    connection = await CC.find_one({"_id": str(cid)}, {"usr": 1})
    user_id = connection.get("usr") if connection else None
    if await has_chat_permission(client, int(cid), user_id, owner=True):
        return user_id
    return None


async def return_json_senpai(query: str, vars_: dict, auth: bool = False, user: int = None):
    url = "https://graphql.anilist.co"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if auth:
        headers["Authorization"] = "Bearer " + str(
            (await AUTH_USERS.find_one({"id": int(user)}))["token"]
        )
    response = await post(url, json={"query": query, "variables": vars_}, headers=headers)
    # AniList uses HTTP 404 for a valid GraphQL query with no matching result.
    # Let the existing search handlers consume that error envelope.
    if response.status == 404:
        try:
            result = response.json()
        except ValueError:
            pass
        else:
            if (
                isinstance(result, dict)
                and isinstance(result.get("errors"), list)
                and result["errors"]
            ):
                return result
    response.raise_for_status()
    return response.json()


def cflag(country):
    if country == "JP":
        return "\U0001f1ef\U0001f1f5"
    if country == "CN":
        return "\U0001f1e8\U0001f1f3"
    if country == "KR":
        return "\U0001f1f0\U0001f1f7"
    if country == "TW":
        return "\U0001f1f9\U0001f1fc"


def pos_no(no):
    ep_ = list(str(no))
    x = ep_.pop()
    if ep_ != [] and ep_.pop() == "1":
        return "th"
    th = "st" if x == "1" else "nd" if x == "2" else "rd" if x == "3" else "th"
    return th


def make_it_rw(time_stamp):
    """Converting Time Stamp to Readable Format"""
    seconds, milliseconds = divmod(int(time_stamp), 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)
    tmp = (
        ((str(days) + " Days, ") if days else "")
        + ((str(hours) + " Hours, ") if hours else "")
        + ((str(minutes) + " Minutes, ") if minutes else "")
        + ((str(seconds) + " Seconds, ") if seconds else "")
        + ((str(milliseconds) + " ms, ") if milliseconds else "")
    )
    return tmp[:-2]


async def get_btns(
    media,
    user: int,
    result: list,
    lsqry: str = None,
    lspage: int = None,
    auth: bool = False,
    sfw: bool = False,
    *,
    client,
):
    buttons = []
    qry = f"_{lsqry}" if lsqry is not None else ""
    pg = f"_{lspage}" if lspage is not None else ""
    if media == "ANIME" and not sfw:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=tr("anime.characters"),
                    callback_data=(f"char_{result[2][0]}_ANI" + f"{qry}{pg}_{str(auth)}_1_{user}"),
                ),
                InlineKeyboardButton(
                    text=tr("anime.description"),
                    callback_data=(f"desc_{result[2][0]}_ANI" + f"{qry}{pg}_{str(auth)}_{user}"),
                ),
                InlineKeyboardButton(
                    text=tr("anime.list_series"),
                    callback_data=(f"ls_{result[2][0]}_ANI" + f"{qry}{pg}_{str(auth)}_{user}"),
                ),
            ]
        )
    if media == "CHARACTER":
        buttons.append(
            [
                InlineKeyboardButton(
                    tr("anime.description"),
                    callback_data=(f"desc_{result[2][0]}_CHAR" + f"{qry}{pg}_{str(auth)}_{user}"),
                )
            ]
        )
        buttons.append(
            [
                InlineKeyboardButton(
                    tr("anime.list_series"),
                    callback_data=f"lsc_{result[2][0]}{qry}{pg}_{str(auth)}_{user}",
                )
            ]
        )
    if media == "SCHEDULED":
        if result[0] != 0 and result[0] != 6:
            buttons.append(
                [
                    InlineKeyboardButton(
                        str(day_(result[0] - 1)),
                        callback_data=f"sched_{result[0] - 1}_{user}",
                    ),
                    InlineKeyboardButton(
                        str(day_(result[0] + 1)),
                        callback_data=f"sched_{result[0] + 1}_{user}",
                    ),
                ]
            )
        if result[0] == 0:
            buttons.append(
                [
                    InlineKeyboardButton(
                        str(day_(result[0] + 1)),
                        callback_data=f"sched_{result[0] + 1}_{user}",
                    )
                ]
            )
        if result[0] == 6:
            buttons.append(
                [
                    InlineKeyboardButton(
                        str(day_(result[0] - 1)),
                        callback_data=f"sched_{result[0] - 1}_{user}",
                    )
                ]
            )
    if media == "MANGA" and not sfw:
        buttons.append([InlineKeyboardButton(tr("anime.more_info"), url=result[1][2])])
    if media == "AIRING" and not sfw:
        buttons.append([InlineKeyboardButton(tr("anime.more_info"), url=result[1][0])])
    if auth is True and media != "SCHEDULED" and not sfw:
        auth_btns = await get_auth_btns(
            media, user, result[2], lspage=lspage, lsqry=lsqry, client=client
        )
        buttons.append(auth_btns)
    if len(result) > 3:
        if result[3] is None:
            if result[4] is not None:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=tr("anime.sequel"),
                            callback_data=f"btn_{result[4]}_{str(auth)}_{user}",
                        )
                    ]
                )
        else:
            if result[4] is not None:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=tr("anime.prequel"),
                            callback_data=f"btn_{result[3]}_{str(auth)}_{user}",
                        ),
                        InlineKeyboardButton(
                            text=tr("anime.sequel"),
                            callback_data=f"btn_{result[4]}_{str(auth)}_{user}",
                        ),
                    ]
                )
            else:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=tr("anime.prequel"),
                            callback_data=f"btn_{result[3]}_{str(auth)}_{user}",
                        )
                    ]
                )
    if (lsqry is not None) and (len(result) != 1):
        if lspage == 1:
            if result[1][1] is True:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=tr("buttons.next_arrow"),
                            callback_data=(
                                f"page_{media}{qry}_{int(lspage) + 1}_{str(auth)}_{user}"
                            ),
                        )
                    ]
                )
            else:
                pass
        elif lspage != 1:
            if result[1][1] is False:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=tr("buttons.previous_arrow"),
                            callback_data=(
                                f"page_{media}{qry}_{int(lspage) - 1}_{str(auth)}_{user}"
                            ),
                        )
                    ]
                )
            else:
                buttons.append(
                    [
                        InlineKeyboardButton(
                            text=tr("buttons.previous_arrow"),
                            callback_data=(
                                f"page_{media}{qry}_{int(lspage) - 1}_{str(auth)}_{user}"
                            ),
                        ),
                        InlineKeyboardButton(
                            text=tr("buttons.next_arrow"),
                            callback_data=(
                                f"page_{media}{qry}_{int(lspage) + 1}_{str(auth)}_{user}"
                            ),
                        ),
                    ]
                )
    return InlineKeyboardMarkup(buttons)


async def get_auth_btns(media, user, data, lsqry: str = None, lspage: int = None, *, client):
    btn = []
    qry = f"_{lsqry}" if lsqry is not None else ""
    pg = f"_{lspage}" if lspage is not None else ""
    if media == "CHARACTER":
        btn.append(
            InlineKeyboardButton(
                text=(
                    tr("anime.add_favs_get_auth_btns")
                    if data[1] is not True
                    else tr("anime.remove_from_favs")
                ),
                callback_data=f"fav_{media}_{data[0]}{qry}{pg}_{user}",
            )
        )
    else:
        btn.append(
            InlineKeyboardButton(
                text=(
                    tr("anime.add_favs_get_auth_btns")
                    if data[3] is not True
                    else tr("anime.remove_from_favs")
                ),
                callback_data=f"fav_{media}_{data[0]}{qry}{pg}_{user}",
            )
        )
        btn.append(
            InlineKeyboardButton(
                text=tr("anime.add_list") if data[1] is False else tr("anime.update_list"),
                callback_data=await list_callback(
                    {
                        "action": "lsadd" if data[1] is False else "lsupdt",
                        "media": media,
                        "media_id": data[0],
                        "list_id": data[2],
                        "query": lsqry,
                        "page": lspage,
                        "owner": int(user),
                    },
                    client=client,
                ),
            )
        )
    return btn


def day_(x: int):
    if x == 0:
        return "Monday"
    if x == 1:
        return "Tuesday"
    if x == 2:
        return "Wednesday"
    if x == 3:
        return "Thursday"
    if x == 4:
        return "Friday"
    if x == 5:
        return "Saturday"
    if x == 6:
        return "Sunday"


def season_(future: bool = False):
    k = datetime.now()
    m = k.month
    if future:
        m = m + 3
    y = k.year
    if m > 12:
        y = y + 1
    if m in [1, 2, 3] or m > 12:
        return "WINTER", y
    if m in [4, 5, 6]:
        return "SPRING", y
    if m in [7, 8, 9]:
        return "SUMMER", y
    if m in [10, 11, 12]:
        return "FALL", y


PIC_LS = deque(maxlen=1000)


async def remove_useless_elements():
    for i in list(PIC_LS):
        try:
            if (await PIC_DB.find_one({"_id": i})) is not None:
                try:
                    PIC_LS.remove(i)
                except ValueError:
                    pass
        except PyMongoError:
            continue


def remove_down_path_files():
    try:
        os.makedirs(Config.DOWN_PATH, exist_ok=True)
        cutoff = time.time() - 3600
        with os.scandir(Config.DOWN_PATH) as entries:
            for entry in entries:
                try:
                    if entry.is_file() and entry.stat().st_mtime < cutoff:
                        os.remove(entry.path)
                except FileNotFoundError:
                    continue
                except OSError:
                    LOGGER.warning("Could not clean download %s", entry.path, exc_info=True)
    except OSError:
        LOGGER.warning("Could not read downloads directory %s", Config.DOWN_PATH, exc_info=True)


j1 = ManagedScheduler(timezone=Config.TIMEZONE)
j1.add_job(remove_useless_elements, "interval", minutes=3)
j1.add_job(remove_down_path_files, "interval", minutes=5)
