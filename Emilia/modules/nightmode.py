from pymongo.errors import PyMongoError
from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle
from pyrogram.errors import RPCError
from pyrogram.types import (
    CallbackQuery,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command
from Emilia.database.nightmode import (
    get_nightchats,
    nightdb,
    nightmode_off,
    nightmode_on,
)
from Emilia.locales import tr
from Emilia.services.scheduler import ManagedScheduler
from Emilia.utils.chat_status import check_user
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess

CLOSE_CHAT = ChatPermissions(
    can_send_messages=False,
    can_send_audios=False,
    can_send_documents=False,
    can_send_photos=False,
    can_send_videos=False,
    can_send_video_notes=False,
    can_send_voice_notes=False,
    can_send_other_messages=False,
    can_send_polls=False,
    can_change_info=False,
    can_add_web_page_previews=False,
    can_pin_messages=False,
    can_invite_users=False,
    can_react_to_messages=False,
    can_edit_tag=False,
    can_manage_topics=False,
)


buttons = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                tr("nightmode.enable_nightmode"),
                callback_data="add_night",
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(tr("nightmode.disable_nightmode"), callback_data="rm_night"),
        ]
    ]
)


@command("nightmode", chat_scope="group")
@anonadmin_checker
async def _nightmode(_, message):
    if not await check_user(message, privileges="can_change_info"):
        return
    return await message.reply(
        text=tr("nightmode.choose_one_option_from_below_buttons"),
        reply_markup=buttons,
    )


@callbackquery(
    filters=filters.regex("^(add_night|rm_night)$"),
    access=CallbackAccess(
        chat_id=lambda client, query: query.message.chat.id,
        privilege="can_change_info",
        denial="nightmode.be_an_admin_first",
    ),
)
async def nightcb(app: Client, query: CallbackQuery):
    data = query.data
    chat_id = query.message.chat.id
    check_night = await nightdb.find_one({"chat_id": chat_id})
    if data == "add_night":
        if check_night:
            return await query.answer(
                text=tr("nightmode.nightmode_has_been_already_enabled_here"),
                show_alert=True,
            )
        await nightmode_on(chat_id)
        await query.answer()
        await query.message.reply(tr("nightmode.enabled_nightmode_for_this_chat"))
        await query.message.delete()
    elif data == "rm_night":
        if not check_night:
            return await query.answer(
                text=tr("nightmode.nightmode_has_been_already_disabled_here"),
                show_alert=True,
            )
        if check_night.get("original_permissions"):
            await _restore_night_permissions(app, check_night)
        await nightmode_off(chat_id)
        await query.answer()
        await query.message.reply(tr("nightmode.disabled_nightmode_for_this_chat"))
        await query.message.delete()


async def start_nightmode(client):
    for chat in await get_nightchats():
        add_chat = int(chat["chat_id"])
        try:
            if not chat.get("original_permissions"):
                current = await client.get_chat(add_chat)
                if current.permissions is None:
                    raise ValueError("Cannot save the group's current permissions")
                permissions = {
                    key: value
                    for key, value in vars(current.permissions).items()
                    if key.startswith("can_") and key != "can_send_media_messages"
                }
                await nightdb.update_one(
                    {"chat_id": add_chat, "original_permissions": {"$exists": False}},
                    {"$set": {"original_permissions": permissions}},
                )
            await client.set_chat_permissions(add_chat, CLOSE_CHAT)
            await client.send_message(
                add_chat,
                text=tr("nightmode.nightmode_12_am_has_been_started_closing"),
            )

        except (RPCError, PyMongoError, OSError, ValueError) as e:
            LOGGER.error(f"Unable To close group {add_chat} - {e}")


async def _restore_night_permissions(client, chat):
    permissions = chat.get("original_permissions")
    if not permissions:
        return False
    chat_id = int(chat["chat_id"])
    await client.set_chat_permissions(chat_id, ChatPermissions(**permissions))
    await nightdb.update_one({"chat_id": chat_id}, {"$unset": {"original_permissions": ""}})
    return True


async def close_nightmode(client):
    for chat in await get_nightchats():
        rm_chat = int(chat["chat_id"])
        try:
            if not await _restore_night_permissions(client, chat):
                continue
            await client.send_message(
                rm_chat,
                text=tr("nightmode.nightmode_6_am_has_been_closed_opening"),
            )
        except (RPCError, PyMongoError, OSError) as e:
            LOGGER.error(f"Unable To restore group permissions {rm_chat} - {e}")


scheduler = ManagedScheduler(timezone=Config.TIMEZONE)


def start_nightmode_scheduler(client):
    scheduler.add_job(start_nightmode, trigger="cron", hour=23, minute=59, args=[client])
    scheduler.add_job(close_nightmode, trigger="cron", hour=6, minute=1, args=[client])
    scheduler.start()
