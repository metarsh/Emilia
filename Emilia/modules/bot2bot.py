from pyrogram import Client, filters
from pyrogram.types import CallbackQuery

from Emilia.custom_filter import callbackquery, command
from Emilia.database.bot2bot import (
    consume_pending_bot_command,
    get_bot2bot_settings,
    set_bot2bot_mode,
    set_bot2bot_skip_review,
)
from Emilia.locales import tr
from Emilia.utils.bot2bot import execute_approved_bot_command, message_fingerprint
from Emilia.utils.chat_status import check_admins, has_chat_permission
from Emilia.utils.client_context import bot_id
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess

BOT2BOT_MODES = {"off", "admin", "all"}
BOT2BOT_TRUE = {"on", "yes", "true"}
BOT2BOT_FALSE = {"off", "no", "false"}


@command("bot2bot")
@anonadmin_checker
async def bot2bot(client, message):
    chat_id = message.chat.id
    if not await check_admins(message, privileges="can_change_info"):
        return

    args = message.text.split()
    if len(args) == 1:
        settings = await get_bot2bot_settings(chat_id)
        await message.reply(
            (
                tr(
                    "bot2bot.bot_bot_command_mode_skip_review",
                    mode=settings["mode"],
                    skip_review="on" if settings["skip_review"] else "off",
                )
            ),
        )
        return

    mode = args[1].lower()
    if mode not in BOT2BOT_MODES:
        await message.reply(tr("bot2bot.choose_one_of_off_admin_all"))
        return

    await set_bot2bot_mode(chat_id, mode)
    await message.reply(tr("bot2bot.bot_to_bot_command_mode_set_to", mode=mode))


@command("bot2botskipreview")
@anonadmin_checker
async def bot2botskipreview(client, message):
    chat_id = message.chat.id
    if not await check_admins(message, privileges="can_change_info"):
        return

    args = message.text.split()
    if len(args) == 1:
        settings = await get_bot2bot_settings(chat_id)
        await message.reply(
            tr(
                "bot2bot.bot_bot_skip_review",
                bot_bot_skip="on" if settings["skip_review"] else "off",
            ),
        )
        return

    value = args[1].lower()
    if value in BOT2BOT_TRUE:
        skip_review = True
    elif value in BOT2BOT_FALSE:
        skip_review = False
    else:
        await message.reply(tr("bot2bot.choose_one_of_on_off_yes_no"))
        return

    await set_bot2bot_skip_review(chat_id, skip_review)
    await message.reply(
        tr("bot2bot.bot_to_bot_skip_review_set_to", bot_bot_skip="on" if skip_review else "off"),
    )


@callbackquery(
    filters=filters.regex("^b2b:(ok|no):"),
    access=CallbackAccess(
        chat_id=lambda client, query: query.message.chat.id,
        denial="bot2bot.only_admins_can_review_bot_commands",
    ),
)
async def bot2bot_review(client: Client, callback_query: CallbackQuery):
    action, token = callback_query.data.split(":")[1:3]
    chat_id = callback_query.message.chat.id
    settings = await get_bot2bot_settings(chat_id)
    if settings["mode"] == "off":
        return await callback_query.answer(
            tr("bot2bot.this_review_request_has_expired"), show_alert=True
        )

    pending = await consume_pending_bot_command(
        token,
        chat_id=chat_id,
        client_bot_id=bot_id(client),
        review_message_id=callback_query.message.id,
    )
    if not pending:
        await callback_query.answer(tr("bot2bot.this_review_request_has_expired"), show_alert=True)
        return
    if action == "no":
        await callback_query.message.edit_text(tr("bot2bot.bot_command_rejected"))
        return

    original = await client.get_messages(
        pending["chat_id"],
        pending["message_id"],
    )
    if (
        not original
        or not original.from_user
        or original.from_user.id != pending["bot_id"]
        or pending.get("source_hash") != message_fingerprint(original)
    ):
        await callback_query.message.edit_text(tr("bot2bot.bot_command_could_not_be_verified"))
        return

    if settings["mode"] == "admin":
        if not await has_chat_permission(client, chat_id, original.from_user.id):
            return await callback_query.message.edit_text(
                tr("bot2bot.bot_command_could_not_be_verified")
            )

    executed = await execute_approved_bot_command(
        client,
        original,
        reviewer_id=callback_query.from_user.id,
    )
    await callback_query.message.edit_text(
        tr("bot2bot.bot_command_approved_executed")
        if executed
        else tr("bot2bot.bot_command_approved_but_no_handler_accepted")
    )
