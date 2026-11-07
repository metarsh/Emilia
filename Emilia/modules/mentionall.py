import asyncio

from pyrogram.errors import FloodWait

from Emilia.config import Config
from Emilia.custom_filter import command, listen
from Emilia.locales import tr
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.command_policy import check_chat_scope, enforce_rate_limit


async def _mentionall(client, message):
    if not await is_user_admin(
        message, user_id=message.from_user.id if message.from_user else None, silent=False
    ):
        return

    text = " "
    reply = message.reply_to_message

    if reply:
        text = reply.text or reply.caption or " "

    elif getattr(message, "matches", None) and message.matches[0].group(1):
        text = message.text.split(None, 1)[1]

    usrnum = 0
    usrtxt = ""
    async for member in client.get_chat_members(message.chat.id):
        usr = member.user
        if getattr(usr, "is_deleted", False):
            continue

        usrnum += 1
        first_name = (usr.first_name or "Unknown").replace("[", "").replace("]", "")
        usrtxt += tr("mentionall.tg_user_id", user_name=first_name, user_id=usr.id)
        if usrnum == 5:
            try:
                await client.send_message(
                    message.chat.id,
                    tr("mentionall.mentionall_message_mentions", message=usrtxt, mentions=text),
                )
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)
                await client.send_message(
                    message.chat.id,
                    tr("mentionall.mentionall_message_mentions", message=usrtxt, mentions=text),
                )
            await asyncio.sleep(5)
            usrnum = 0
            usrtxt = ""

    # flush the final partial batch (member count not a multiple of 5)
    if usrtxt:
        try:
            await client.send_message(
                message.chat.id,
                tr("mentionall.mentionall_message_mentions", message=usrtxt, mentions=text),
            )
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)
            await client.send_message(
                message.chat.id,
                tr("mentionall.mentionall_message_mentions", message=usrtxt, mentions=text),
            )


@command("all", chat_scope="group", rate_limit=Config.RATE_LIMIT_SUPER_HEAVY)
async def mentionall(client, message):
    await _mentionall(client, message)


@listen()
async def mentionall_watcher(client, message):
    if not message.text or not message.text.startswith("@all"):
        return
    if not await check_chat_scope(message, "group"):
        return
    if not await enforce_rate_limit(
        client,
        message,
        f"{mentionall.__module__}.{mentionall.__qualname__}",
        Config.RATE_LIMIT_SUPER_HEAVY,
    ):
        return
    await _mentionall(client, message)
