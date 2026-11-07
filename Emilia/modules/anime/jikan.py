# uses jikanpy (Jikan API)
from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.utils.anime import get_btns, get_user_from_channel, sender_id
from Emilia.utils.anime_data import get_scheduled
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess, remember_menu


@command("schedule", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def scheduled_anime(client: Client, message: Message):
    """Get List of Scheduled Anime"""
    gid = message.chat.id
    x = await client.send_message(gid, tr("jikan.code_fetching_scheduled_animes_code"))
    user = sender_id(message)
    msg = await get_scheduled()
    buttons = await get_btns("SCHEDULED", result=[msg[1]], user=user, client=client)
    await remember_menu(x, user, client=client)
    await x.edit_text(msg[0], reply_markup=buttons)


@callbackquery(
    filters=filters.regex(pattern="sched_(.*)"),
    access=CallbackAccess(account_resolver=get_user_from_channel),
)
async def schedule_page(client: Client, cq: CallbackQuery):
    await cq.answer()
    kek, day, user = cq.data.split("_")
    msg = await get_scheduled(int(day))
    buttons = await get_btns("SCHEDULED", result=[int(day)], user=user, client=client)
    await cq.edit_message_text(msg[0], reply_markup=buttons)
