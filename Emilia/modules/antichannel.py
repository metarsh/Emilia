from pyrogram import Client, enums, filters
from pyrogram.errors import RPCError
from redis.exceptions import RedisError

from Emilia.application import db
from Emilia.custom_filter import command
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import bot_has_permission, check_user
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.linked_chat import get_linked_channel

# db
antichanneldb = db.antichannel


async def antichannelmode_on(chat_id: int):
    return await atomic_upsert(antichanneldb, {"chat_id": chat_id}, {"$set": {"chat_id": chat_id}})


async def antichannelmode_off(chat_id: int):
    return await antichanneldb.delete_one({"chat_id": chat_id})


async def isModOn(chat_id: int) -> bool:
    return bool(await antichanneldb.find_one({"chat_id": chat_id}))


@command(["antichannel", "antichannelmode"], chat_scope="group", allow_connected=True)
@anonadmin_checker
@log_to_channel
async def _antichannelmode(_, message):
    chat_id = effective_chat_id(message)

    if not await check_user(message, privileges="can_change_info"):
        return

    args = message.text.split()
    mm = await isModOn(chat_id)
    if len(args) < 2:
        await reply_usage(message, _antichannelmode)
    if "on" in args:
        if not mm:
            await antichannelmode_on(chat_id)
            await message.reply_text(tr("antichannel.antichannel_is_enabled_in_this_group"))
            return "ENABLED_ANTICHANNEL", None, None
        return await message.reply_text(
            tr("antichannel.antichannel_is_already_enabled_in_this_group")
        )
    elif "off" in args:
        if not mm:
            return await message.reply_text(
                tr("antichannel.antichannel_is_already_disabled_in_this_group")
            )
        await antichannelmode_off(chat_id)
        await message.reply_text(tr("antichannel.disabled_antichannel_successfully_in_this_chat"))
        return "DISABLED_ANTICHANNEL", None, None


@Client.on_message(filters.group, group=110)
async def _message_handler(client, message):
    if not (await isModOn(message.chat.id)):
        return
    chat_id = message.chat.id
    if message.sender_chat and message.sender_chat.type == enums.ChatType.CHANNEL:
        try:
            linked_channel = await get_linked_channel(client, chat_id, fresh=True)
            if message.sender_chat.id == linked_channel:
                return
            if not await bot_has_permission(
                message, privileges=["can_delete_messages", "can_restrict_members"], silent=True
            ):
                return
            await client.ban_chat_member(chat_id, message.sender_chat.id)
            await message.delete()
        except (RPCError, RedisError, OSError):
            await message.reply_text(tr("antichannel.give_me_ban_delete_permissions_to_ban"))
