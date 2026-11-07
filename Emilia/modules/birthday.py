import datetime
import random

from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import RPCError

from Emilia.application import LOGGER, pgram
from Emilia.custom_filter import command
from Emilia.database import birthday as db
from Emilia.locales import tr
from Emilia.utils.anime import j1 as scheduler
from Emilia.utils.chat_status import check_user
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.get_user import mention_html, resolve_target
from Emilia.utils.message_actor import actor_id, actor_user

BIRTHDAY_WISHES = [
    tr("birthday.happy_birthday_may_day_filled_joy_laughter"),
    tr("birthday.wishing_very_happy_birthday_have_fantastic_year_ahead"),
    tr("birthday.happy_birthday_hope_all_birthday_wishes_come_true"),
    tr("birthday.many_happy_returns_day_enjoy_special_day"),
    tr("birthday.happy_birthday_may_year_bring_success_happiness"),
    tr("birthday.happy_birthday_eat_lots_cake_have_fun"),
    tr("birthday.wishing_happiest_birthdays"),
    tr("birthday.happy_birthday_shine_bright_like_diamond_today"),
]


@command("setbirthday")
async def set_birthday_handler(client, message):
    args = (message.text or "").split(None, 1)
    if len(args) < 2:
        await reply_usage(message)
        return

    date_str = args[1]
    try:
        date = datetime.datetime.strptime(date_str, "%d/%m")
        day = date.day
        month = date.month
    except ValueError:
        await message.reply_text(tr("birthday.invalid_format_please_use_dd_mm"))
        return

    chat_id = message.chat.id if message.chat.type != ChatType.PRIVATE else None
    sender_id = message.from_user.id if message.from_user else None
    await db.set_birthday(sender_id, day, month, chat_id)

    msg = tr("birthday.birthday_set", day=day, month=month)
    if chat_id:
        msg += tr("birthday.will_wish_group")
    await message.reply_text(msg)


@command("addbirthday", chat_scope="group")
@anonadmin_checker
async def add_birthday_handler(client, message):

    sender_id = actor_id(message) if actor_user(message) else None
    if not await check_user(message, user_id=sender_id, privileges="can_change_info"):
        return

    user, date_str = await resolve_target(message)
    if not date_str:
        await reply_usage(message)
        return
    if user is None:
        await message.reply_text(tr("birthday.user_not_found"))
        return
    user_id = user.id

    try:
        date = datetime.datetime.strptime(date_str, "%d/%m")
        day = date.day
        month = date.month
    except ValueError:
        await message.reply_text(tr("birthday.invalid_format_please_use_dd_mm"))
        return

    await db.set_birthday(user_id, day, month, message.chat.id)
    await message.reply_text(
        tr(
            "birthday.birthday_set_will_wish_them_group",
            user_name=user.first_name,
            day=day,
            month=month,
        )
    )


@command("birthday")
async def get_birthday_handler(client, message):
    user, _ = await resolve_target(message, default_to_sender=True)
    if user is None:
        await message.reply_text(tr("birthday.user_not_found"))
        return
    user_id = user.id

    data = await db.get_birthday(user_id)
    if data:
        await message.reply_text(tr("birthday.birthday", day=data["day"], month=data["month"]))
    else:
        await message.reply_text(tr("birthday.birthday_not_set"))


@command("delbirthday")
async def del_birthday_handler(client, message):
    sender_id = message.from_user.id if message.from_user else None
    await db.delete_birthday(sender_id)
    await message.reply_text(tr("birthday.birthday_deleted"))


async def check_birthdays():
    from zoneinfo import ZoneInfo

    from Emilia.config import Config

    today = datetime.datetime.now(ZoneInfo(Config.TIMEZONE))
    day = today.day
    month = today.month

    async for b in db.get_birthdays_by_date(day, month):
        user_id = b["user_id"]
        chats = b.get("chats", [])

        wish = random.choice(BIRTHDAY_WISHES)

        # Try to get user name
        try:
            user = await pgram.get_users(user_id)
            name = user.first_name
        except (RPCError, OSError):
            name = "User"

        mention = mention_html(user_id, name, client=pgram)
        text = tr("birthday.happy_birthday", wish=wish, user_mention=mention)

        # Send to chats
        for chat_id in chats:
            try:
                await pgram.send_message(chat_id, text, parse_mode=ParseMode.HTML)
            except (RPCError, OSError) as e:
                LOGGER.error(
                    f"Failed to send birthday message to chat {chat_id} for user {user_id}: {e}"
                )

        # If no chats, send PM
        if not chats:
            try:
                await pgram.send_message(user_id, wish)
            except (RPCError, OSError) as e:
                LOGGER.error(f"Failed to send birthday PM to {user_id}: {e}")


scheduler.add_job(check_birthdays, "cron", hour=0, minute=0)
