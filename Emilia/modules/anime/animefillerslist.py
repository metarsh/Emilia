from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.utils.anime import get_user_from_channel, rand_key, sender_id
from Emilia.utils.anime_data import parse_filler, search_filler
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess, remember_menu
from Emilia.utils.query_cache import QueryCache

FILLERS = QueryCache()
MAX_CHOICES = 20


def _format_filler_result(title, result):
    text = tr("animefillerslist.fillers_anime", req=title)
    for field, label in (
        ("total_ep", "animefillerslist.manga_canon_episodes"),
        ("mixed_ep", "animefillerslist.mixed_canon_fillers_filler_btn"),
        ("filler_ep", "animefillerslist.filler_episodes"),
        ("ac_ep", "animefillerslist.anime_canon_episodes_filler_btn"),
    ):
        if field == "ac_ep" and result.get(field) is None:
            continue
        text += tr(label) + (result.get(field) or tr("animefillerslist.not_listed"))
    return text


@command("fillers", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def fillers_cmd(client: Client, message: Message):
    user = sender_id(message)
    qry = (message.text or message.caption or "").split(maxsplit=1)
    if len(qry) == 1:
        return await reply_usage(message)
    k = await search_filler(qry[1])
    if not k:
        return await message.reply_text(tr("animefillerslist.no_fillers_found_for_the_given_anime"))
    if len(k) == 1:
        title, slug = next(iter(k.items()))
        return await message.reply_text(_format_filler_result(title, await parse_filler(slug)))
    buttons = []
    for title, slug in list(k.items())[:MAX_CHOICES]:
        fl_js = rand_key()
        FILLERS[fl_js] = [slug, title]
        buttons.append([InlineKeyboardButton(title, callback_data=f"fill_{fl_js}_{user}")])
    text = tr("animefillerslist.pick_anime_you_want_to_see_fillers")
    if len(k) > MAX_CHOICES:
        text += tr("animefillerslist.refine_search", count=MAX_CHOICES)
    sent = await message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    await remember_menu(sent, user, client=client)


@callbackquery(
    filters=filters.regex(pattern="^fill_[a-f0-9]{8}_-?\\d+$"),
    access=CallbackAccess(account_resolver=get_user_from_channel),
)
async def filler_btn(client: Client, cq: CallbackQuery):
    cq._emilia_handled = True
    _, req, _ = cq.data.split("_")
    selection = FILLERS.get(req)
    if selection is None:
        return await cq.answer(tr("custom_filter.this_button_has_expired"), show_alert=True)
    await cq.answer()
    result = await parse_filler(selection[0])
    await cq.edit_message_text(_format_filler_result(selection[1], result))
