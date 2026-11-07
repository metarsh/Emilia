import html

from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.custom_filter import CONNECTED_COMMANDS, callbackquery, command
from Emilia.database.connection import connectDB
from Emilia.locales import tr
from Emilia.utils.client_context import bot_username
from Emilia.utils.command_help import reply_usage
from Emilia.utils.command_policy import CHAT_SCOPES
from Emilia.utils.connections import accessible_chat, connection
from Emilia.utils.menu_guard import CallbackAccess


def connection_commands(chat):
    return sorted(
        name for name, scope in CONNECTED_COMMANDS.items() if chat.type in CHAT_SCOPES[scope]
    )


async def show_connection(client, message, chat):
    text = tr("connect.have_connected", chat_title=html.escape(chat.title or str(chat.id)))
    text += "\n\n" + tr("connection.supported_commands") + "\n"
    text += " ".join(f"/{name}" for name in connection_commands(chat))
    rows = [[InlineKeyboardButton(tr("connection.refresh"), callback_data="connect_refresh")]]
    return await message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))


@command("connect")
async def Connect(client, message):
    if message.chat.type == ChatType.PRIVATE:
        args = message.command or []
        if len(args) != 2:
            return await reply_usage(message, Connect)
        return await connect_button(client, message, args[1])
    if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL):
        return
    await message.reply_text(
        tr("connect.tap_the_following_button_to_connect_to"),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("connect.connect_to_chat"),
                        url=f"https://t.me/{bot_username(client)}?start=connect_{message.chat.id}",
                        style=ButtonStyle.SUCCESS,
                    )
                ]
            ]
        ),
    )


async def connectRedirect(client, message):
    if message.chat.type != ChatType.PRIVATE or not message.from_user:
        return
    args = message.command or []
    if len(args) < 2 or not args[1].startswith("connect_"):
        return await reply_usage(message, Connect)
    return await connect_button(client, message, args[1].removeprefix("connect_"))


async def connect_button(client, message, peer):
    if message.chat.type != ChatType.PRIVATE or not message.from_user:
        return False
    chat = await accessible_chat(client, message.from_user.id, peer)
    if chat is None:
        await message.reply_text(tr("connection.access_denied"))
        return False
    await connectDB(message.from_user.id, chat.id)
    await show_connection(client, message, chat)
    return True


@callbackquery(
    pattern=r"^connect_(?:user|admin|refresh)$",
    access=CallbackAccess(user_id=lambda client, query: query.message.chat.id),
)
async def refresh_connection(client, query):
    if query.message.chat.type != ChatType.PRIVATE:
        return await query.answer(tr("errors.private_only"), show_alert=True)
    if await connection(query) is None:
        return await query.answer(
            tr("connection.you_aren_t_connected_to_any_chat"), show_alert=True
        )
    await query.answer()
    await show_connection(client, query.message, query.message._emilia_target_chat)
    await query.message.delete()
