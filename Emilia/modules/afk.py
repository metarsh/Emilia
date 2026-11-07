import random
import time

from pyrogram.enums import ChatType, MessageEntityType
from pyrogram.errors import (
    FloodWait,
    PeerIdInvalid,
    UsernameInvalid,
    UsernameNotOccupied,
)

from Emilia.config import Config
from Emilia.custom_filter import listen
from Emilia.database import afk as db
from Emilia.locales import tr
from Emilia.utils.admins import get_time as get_readable_time

options = [
    tr("afk.here_afk"),
    tr("afk.back_away"),
    tr("afk.now_chat_back_after"),
    tr("afk.awake_afk"),
    tr("afk.back_online_away"),
    tr("afk.finally_here_afk"),
    tr("afk.welcome_back_afk"),
    tr("afk.where_chat_afk"),
    tr("afk.pro_back_alive_afk"),
]


@listen()
async def afk(client, message):
    if message.chat.id == 777000:
        return
    if not message.from_user:
        return
    text = message.text or ""
    for x in ["+afk", "/afk", "!afk", "?afk", ".afk", "brb", tr("afk.go_away")]:
        if text.lower().startswith(x):
            try:
                reason = text.split(None, 1)[1]
            except IndexError:
                reason = ""
            if text.lower().startswith("i go away"):
                reason = reason.replace("go away", "")
            _x = await message.reply_text(
                tr("afk.now_away_from_keyboard", user_name=message.from_user.first_name),
            )
            await db.set_afk(message.from_user.id, message.from_user.first_name, reason)
            return

    afk_data = await db.get_afk_user(message.from_user.id)
    if afk_data and "time" in afk_data:
        xp = get_readable_time(int(time.time()) - int(afk_data.get("time")))
        await db.unset_afk(message.from_user.id)
        await message.reply_text(random.choice(options).format(message.from_user.first_name, xp))
        return


@listen()
async def afk_check(client, message):
    if (
        message.chat.type == ChatType.PRIVATE
        or not message.from_user
        or message.from_user.id == Config.BOT_ID
    ):
        return

    user_id = None
    r = message.reply_to_message
    if r and r.from_user:
        user_id = r.from_user.id
    else:
        text = message.text or message.caption or ""
        for ent in message.entities or message.caption_entities or []:
            if ent.offset != 0:
                break
            if ent.type == MessageEntityType.TEXT_MENTION and ent.user:
                user_id = ent.user.id
                break
            if ent.type == MessageEntityType.MENTION:
                mention = text[ent.offset : ent.offset + ent.length]
                try:
                    user_id = (await client.get_users(mention.split()[0])).id
                except AttributeError:
                    user_id = None
                except ValueError:
                    user_id = None
                except FloodWait:
                    user_id = None
                except (
                    PeerIdInvalid,
                    UsernameInvalid,
                    UsernameNotOccupied,
                    IndexError,
                ):
                    # pyrogram raises these instead of ValueError for bad
                    # usernames
                    user_id = None
                break

    if not user_id:
        return

    afk_data = await db.get_afk_user(user_id)
    if afk_data and afk_data["time"]:
        time_seen = get_readable_time(int(time.time()) - int(afk_data["time"]))
        reason = f"**Reason**: `{afk_data['reason']}`" if afk_data["reason"] else ""
        await message.reply_text(
            tr(
                "afk.away_from_keyboard_last_seen_ago",
                user_name=afk_data["first_name"],
                elapsed=time_seen,
                reason=reason,
            ),
        )
