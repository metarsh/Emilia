from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.utils.anime import get_user_from_channel, query_identity
from Emilia.utils.anime_data import get_wo, get_wols
from Emilia.utils.cb_token import stash, unstash
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess, remember_menu


def _search_keyboard(results, token):
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(str(title), callback_data=f"watch:{identifier}:0:{token}")]
            for identifier, title in results
        ]
    )


async def _watch_payload(client, query, token):
    payload = await unstash(
        token,
        client=client,
        user_id=query.from_user.id,
        chat_id=query.message.chat.id,
        message_id=query.message.id,
    )
    if payload is None:
        await query.answer(tr("watch.this_button_expired_run_the_command_again"), show_alert=True)
        return None
    return payload


@command("watch", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def get_watch_order(client: Client, message: Message):
    chat_id = message.chat.id
    arguments = (message.text or message.caption or "").split(maxsplit=1)
    if len(arguments) == 1:
        return await reply_usage(message)
    results = await get_wols(arguments[1])
    if not results:
        return await message.reply_text(tr("anime.no_results_found"))
    owner, account = await query_identity(message)
    sent = await message.reply_text(tr("watch.found_related_animes_query", query=arguments[1]))
    await remember_menu(sent, owner, client=client)
    token = await stash(
        {"qry": arguments[1]},
        client=client,
        user_id=account,
        chat_id=chat_id,
        message_id=sent.id,
    )
    await sent.edit_reply_markup(_search_keyboard(results, token))


@callbackquery(
    filters=filters.regex("^watch:\\d+:\\d+:[A-Za-z0-9_-]+$"),
    access=CallbackAccess(account_resolver=get_user_from_channel),
)
async def watch_page(client: Client, query: CallbackQuery):
    _, identifier, page, token = query.data.split(":")
    if await _watch_payload(client, query, token) is None:
        return
    page = int(page)
    text, total = await get_wo(int(identifier), page)
    last_page = max(0, (total - 1) // 50)
    if page > last_page:
        return await query.answer(tr("tracemoepy.out_of_range"), show_alert=True)
    navigation = []
    if page:
        navigation.append(
            InlineKeyboardButton(
                tr("buttons.previous"), callback_data=f"watch:{identifier}:{page - 1}:{token}"
            )
        )
    if page < last_page:
        navigation.append(
            InlineKeyboardButton(
                tr("buttons.next"), callback_data=f"watch:{identifier}:{page + 1}:{token}"
            )
        )
    rows = [navigation] if navigation else []
    rows.append(
        [
            InlineKeyboardButton(
                tr("buttons.back"), callback_data=f"watch-back:{token}", style=ButtonStyle.PRIMARY
            )
        ]
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(rows))
    await query.answer()


@callbackquery(
    filters=filters.regex("^watch-back:[A-Za-z0-9_-]+$"),
    access=CallbackAccess(account_resolver=get_user_from_channel),
)
async def watch_search(client: Client, query: CallbackQuery):
    token = query.data.split(":", 1)[1]
    payload = await _watch_payload(client, query, token)
    if payload is None:
        return
    results = await get_wols(payload["qry"])
    await query.edit_message_text(
        tr("watch.found_related_animes_query", query=payload["qry"]),
        reply_markup=_search_keyboard(results, token),
    )
    await query.answer()
