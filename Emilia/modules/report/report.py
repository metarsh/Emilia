from pyrogram import Client, enums, filters

from Emilia.custom_filter import command
from Emilia.database.report import get_report
from Emilia.locales import tr
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.get_user import mention_html


async def report_(client, message):
    chat_id = message.chat.id

    if not (await get_report(chat_id)):
        return

    if await is_user_admin(message, silent=True):
        return await message.reply(tr("report.you_re_an_admin_here_why_d"))

    if not message.reply_to_message:
        return await message.reply(tr("report.which_user_you_want_to_report"))

    if await is_user_admin(message.reply_to_message, silent=True):
        return await message.reply(tr("report.you_can_t_report_admin"))

    reported_user = message.reply_to_message.from_user
    if reported_user is None or message.reply_to_message.sender_chat:
        return await message.reply(tr("errors.user_not_found"))

    admin_data = client.get_chat_members(
        chat_id=chat_id, filter=enums.ChatMembersFilter.ADMINISTRATORS
    )

    ADMINS_TAG = ""
    TAG = "\u200b"
    async for admin in admin_data:
        if not admin.user.is_bot:
            ADMINS_TAG += mention_html(admin.user.id, TAG, client=client)

    await message.reply(
        tr("report.reported_admins", user_mention=reported_user.mention, admins_tag=ADMINS_TAG)
    )


@command("report", chat_scope="group")
async def report(client, message):
    await report_(client, message)


@Client.on_message(filters.group & filters.regex(pattern=(r"(?i)@admin(s)?")))
async def regex_report(client, message):
    await report_(client, message)
