import asyncio
from datetime import datetime
from io import BytesIO

from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.errors import ChannelInvalid as ci
from pyrogram.errors import ChannelPrivate as cp
from pyrogram.errors import FloodWait as fw
from pyrogram.errors import PeerIdInvalid as pi
from pyrogram.types import (
    CallbackQuery,
    ChatAdministratorRights,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from Emilia.application import db
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command, listen
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.locales.help import ANIME_HELP, HELP_PAGES, HelpPage
from Emilia.utils.allowlist import is_telegram_invite_url
from Emilia.utils.anime import AUTH_USERS, get_user_from_channel
from Emilia.utils.chat_status import has_chat_permission
from Emilia.utils.client_context import bot_username
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.forward_origin import fwd_chat
from Emilia.utils.get_user import normalize_peer
from Emilia.utils.help_rendering import show_help_page
from Emilia.utils.menu_guard import CallbackAccess, remember_menu
from Emilia.utils.message_actor import actor_user
from Emilia.utils.operator import evaluate_command, operator_only, terminal_command

USERS = db["USERS"]
CHATS = db.chats
SFW_GROUPS = db["SFW_GROUPS"]
AG = db["AIRING_GROUPS"]
HD_GRPS = db["HEADLINES_GROUPS"]
MAL_HD_GRPS = db["MAL_HEADLINES_GROUPS"]
SP_GRPS = db["SUBSPLEASE_GROUPS"]
CC = db["CONNECTED_CHANNELS"]


@command("anidbcleanup", chat_scope="private", access="developer")
@operator_only
async def db_cleanup(client: Client, message: Message):
    count = 0
    entries = ""
    st = datetime.now()
    x = await message.reply_text(tr("anime.bot.starting_database_cleanup_in_5_seconds"))
    et = datetime.now()
    pt = (et - st).microseconds / 1000
    await asyncio.sleep(5)
    await x.edit_text(tr("anime.bot.checking_1st_collection"))
    async for i in CHATS.find():
        await asyncio.sleep(2)
        try:
            await client.get_chat(i["chat_id"])
        except (cp, ci, pi):
            count += 1
            entries += str(await CHATS.find_one({"chat_id": i["chat_id"]})) + "\n\n"
            await CHATS.find_one_and_delete({"chat_id": i["chat_id"]})
            await SFW_GROUPS.find_one_and_delete({"id": i["chat_id"]})
            await AG.find_one_and_delete({"_id": i["chat_id"]})
            await HD_GRPS.find_one_and_delete({"_id": i["chat_id"]})
            await SP_GRPS.find_one_and_delete({"_id": i["chat_id"]})
        except fw as error:
            await asyncio.sleep(error.value)
    await asyncio.sleep(5)
    await x.edit_text(tr("anime.bot.checking_2nd_collection"))
    async for i in AUTH_USERS.find({"id": {"$type": ["int", "long"]}}):
        await asyncio.sleep(2)
        try:
            await client.get_users(i["id"])
        except pi:
            count += 1
            entries += str(await AUTH_USERS.find_one({"id": i["id"]})) + "\n\n"
            await AUTH_USERS.find_one_and_delete({"id": i["id"]})
        except fw as error:
            await asyncio.sleep(error.value)
    await asyncio.sleep(5)

    nosgrps = await CHATS.estimated_document_count()
    nossgrps = await SFW_GROUPS.estimated_document_count()
    nosauus = await AUTH_USERS.estimated_document_count()
    if count == 0:
        msg = tr(
            "anime.bot.database_seems_accurate_no_changes_made_groups_sfw",
            groups=nosgrps,
            sfw_groups=nossgrps,
            authorized_users=nosauus,
            ping=pt,
        )
    else:
        msg = tr(
            "anime.bot.entries_removed_from_database_new_data_groups_sfw",
            removed_count=count,
            groups=nosgrps,
            sfw_groups=nossgrps,
            authorized_users=nosauus,
            ping=pt,
        )
        if len(entries) > 4095:
            document = BytesIO(entries.encode())
            document.name = "removed-records.txt"
            await x.reply_document(document)
        else:
            await x.reply_text(entries)
    await x.edit_text(msg)


@command("anihelp", disable=True)
@anonadmin_checker(named=True, allow_channel=True)
async def anime_help(client: Client, message: Message):
    gid = message.chat.id
    bot_us = bot_username(client)
    if actor_user(message) is not None:
        id_ = actor_user(message).id
    else:
        await show_help_page(
            client,
            message,
            HelpPage("anime", "Anime", tr("anime.bot.click_below_button_for_bot_help")),
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("buttons.help"),
                            url=f"https://t.me/{bot_us}/?start=anihelp",
                            style=ButtonStyle.PRIMARY,
                        )
                    ]
                ]
            ),
        )
        return
    buttons = anime_help_keyboard(id_)
    text = tr("anime.bot.small_guide_how_use_basic_commands_use_ping")
    if gid == id_ or id_ in Config.DEV_USERS:
        sent = await show_help_page(client, message, HelpPage("anime", "Anime", text), buttons)
        if sent is not None:
            await remember_menu(sent, id_, client=client)
    else:
        await show_help_page(
            client,
            message,
            HelpPage("anime", "Anime", tr("anime.bot.click_below_button_for_bot_help")),
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("buttons.help"),
                            url=f"https://t.me/{bot_username(client)}/?start=anihelp",
                            style=ButtonStyle.PRIMARY,
                        )
                    ]
                ]
            ),
        )


_CONNECTION_ACTIONS = {
    87101: "aniconnect",
    87102: "aniconnect",
    87103: "anidisconnect",
    87104: "anidisconnect",
}


async def _connection_picker(message, action):
    first_id = 87101 if action == "aniconnect" else 87103
    buttons = [
        [
            KeyboardButton(
                tr("anime.choose_channel" if channel else "anime.choose_group"),
                request_chat=KeyboardButtonRequestChat(
                    button_id=first_id + int(channel),
                    chat_is_channel=channel,
                    chat_is_created=True,
                    bot_is_member=True,
                    bot_administrator_rights=(
                        ChatAdministratorRights(can_manage_chat=True)
                        if action == "aniconnect"
                        else None
                    ),
                ),
            )
        ]
        for channel in (False, True)
    ]
    return await message.reply_text(
        tr(
            "anime.choose_chat_to_connect"
            if action == "aniconnect"
            else "anime.choose_chat_to_disconnect"
        ),
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True),
    )


async def _set_channel_connection(client, message, peer, action, *, from_picker=False):
    chat = await client.get_chat(peer)
    if chat.type not in (ChatType.CHANNEL, ChatType.GROUP, ChatType.SUPERGROUP):
        return await message.reply_text(tr("errors.group_only"))
    target = chat.id
    if not await has_chat_permission(client, target, message.from_user.id, owner=True):
        return await message.reply_text(tr("anime.channel_owner_required"))
    if action == "aniconnect":
        await atomic_upsert(CC, {"_id": str(target)}, {"$set": {"usr": message.from_user.id}})
        text = tr("anime.bot.successfully_connected_the_channel")
    else:
        result = await CC.delete_one({"_id": str(target)})
        text = tr(
            "anime.bot.successfully_disconnected_the_channel"
            if result.deleted_count
            else "anime.bot.channel_not_connected"
        )
    options = {"reply_markup": ReplyKeyboardRemove()} if from_picker else {}
    await message.reply_text(text, **options)


@command(["aniconnect", "anidisconnect"], disable=True)
async def connect_channel(client: Client, message: Message):
    if not message.from_user or message.sender_chat:
        return await message.reply_text(
            tr("anime.bot.go_to_bot_pm_to_connect_channel"),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("anime.bot.bot_pm"), url=f"https://t.me/{bot_username(client)}"
                        )
                    ]
                ]
            ),
        )
    command = message.command[0]
    if message.chat.type == ChatType.PRIVATE:
        arguments = (message.text or message.caption or "").split(maxsplit=1)
        if len(arguments) != 2:
            forwarded = fwd_chat(message.reply_to_message) if message.reply_to_message else None
            if forwarded is None:
                return await _connection_picker(message, command)
            peer = forwarded.id
        else:
            peer = normalize_peer(arguments[1].strip())
            if is_telegram_invite_url(str(peer)):
                return await _connection_picker(message, command)
    else:
        peer = message.chat.id
    await _set_channel_connection(client, message, peer, command)


@listen(filters=filters.private & filters.chat_shared, name="anime_chat_selection")
async def connect_shared_channel(client: Client, message: Message):
    if not message.from_user or message.sender_chat or message.forward_origin:
        return
    action = _CONNECTION_ACTIONS.get(message.chat_shared.button_id)
    if action is None:
        return
    await _set_channel_connection(
        client, message, message.chat_shared.chat.id, action, from_picker=True
    )


@callbackquery(
    filters=filters.regex(pattern="helppp_(.*)"),
    access=CallbackAccess(account_resolver=get_user_from_channel),
)
async def anime_help_page(client: Client, cq: CallbackQuery):
    await cq.answer()
    kek, qry, user = cq.data.split("_")
    page = ANIME_HELP.get(qry)
    if page is None:
        return
    btn = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("buttons.back"),
                    callback_data=f"hlplist_{user}",
                    style=ButtonStyle.PRIMARY,
                )
            ]
        ]
    )
    await show_help_page(client, cq.message, page, btn, edit=True)


@callbackquery(
    filters=filters.regex(pattern="hlplist_(.*)"),
    access=CallbackAccess(account_resolver=get_user_from_channel),
)
async def anime_help_index(client: Client, cq: CallbackQuery):
    await cq.answer()
    user = cq.data.split("_")[1]
    buttons = anime_help_keyboard(user)
    text = tr("anime.bot.small_guide_how_use_basic_commands_use_start")
    await show_help_page(client, cq.message, HelpPage("anime", "Anime", text), buttons, edit=True)


def anime_help_keyboard(user):
    but_rc = []
    buttons = []
    order = dict.fromkeys((*HELP_PAGES["anime"].children, *ANIME_HELP))
    for slug in order:
        page = ANIME_HELP.get(slug)
        if page is None:
            continue
        but_rc.append(InlineKeyboardButton(page.title, callback_data=f"helppp_{page.id}_{user}"))
        if len(but_rc) == 2:
            buttons.append(but_rc)
            but_rc = []
    if len(but_rc) != 0:
        buttons.append(but_rc)
    return InlineKeyboardMarkup(buttons)


@command("anistats", access="developer")
async def anime_stats(client: Client, message: Message):
    st = datetime.now()
    x = await message.reply_text(tr("anime.bot.collecting_stats"))
    et = datetime.now()
    pt = (et - st).microseconds / 1000
    nosus = await USERS.estimated_document_count()
    nosauus = await AUTH_USERS.estimated_document_count()
    nosgrps = await CHATS.estimated_document_count()
    nossgrps = await SFW_GROUPS.estimated_document_count()
    nosmhdgrps = await MAL_HD_GRPS.estimated_document_count()
    s = await SP_GRPS.estimated_document_count()
    await x.edit_text(
        tr(
            "anime.stats_summary",
            users=nosus,
            authorized_users=nosauus,
            groups=nosgrps,
            airing_groups=s,
            headline_groups=nosmhdgrps,
            sfw_groups=nossgrps,
            ping=pt,
        )
    )


@command("feedback", chat_scope="private")
async def feedback(client: Client, message: Message):
    owner = (await client.get_users(Config.OWNER_ID)).username
    await client.send_message(
        message.chat.id,
        tr("anime.bot.for_issues_or_queries_please_contact") + tr("anime.bot.join", owner=owner),
    )


@command("anieval", access="developer")
@operator_only
async def anime_eval(client: Client, message: Message):
    return await evaluate_command(client, message)


@command("term", access="developer")
@operator_only
async def terminal(client: Client, message: Message):
    return await terminal_command(client, message)
