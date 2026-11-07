from pyrogram import filters
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.errors import RPCError
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
)

from Emilia.application import db
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.modules.anime.anilist import auth_link_cmd, logout_cmd
from Emilia.modules.anime.bot import anime_help
from Emilia.modules.connection.connect import connectRedirect
from Emilia.modules.greetings.captcha.button_captcha import (
    buttonCaptchaRedirect,
)
from Emilia.modules.greetings.captcha.text_captcha import textCaptchaRedirect
from Emilia.modules.greetings.group_onboarding import (
    onboarding_redirect,
    starter_redirect,
)
from Emilia.modules.music.playlist.deeplink import (
    playlist_menu_redirect,
    playlist_redirect,
)
from Emilia.modules.notes.private_notes import note_redirect
from Emilia.modules.requests import request_redirect
from Emilia.modules.rules.rules import rulesRedirect
from Emilia.utils.anime import AUTH_USERS, get_btns
from Emilia.utils.anime_data import anime_error, get_additional_info, get_anime, get_recommendations
from Emilia.utils.client_context import bot_name, bot_username
from Emilia.utils.decorators import leavemute
from Emilia.utils.menu_guard import CallbackAccess, remember_menu


async def build_start_message(client):
    current_bot_id = int(client.bot_token.split(":")[0])

    custom_start_pic = None
    pic_data = await db.startpic.find_one({"bot_id": current_bot_id})
    if pic_data:
        custom_start_pic = pic_data.get("file_id") or pic_data.get("url")
    photo = custom_start_pic
    start_pic_url = (
        custom_start_pic
        if custom_start_pic and custom_start_pic.startswith(("http://", "https://"))
        else Config.START_PIC
    )

    buttons = [
        [
            InlineKeyboardButton(
                tr("buttons.help"), callback_data="help:list:0", style=ButtonStyle.PRIMARY
            )
        ],
        [InlineKeyboardButton(tr("start.how_to_clone"), callback_data="clone_help")],
    ]
    links = []
    if Config.SUPPORT_CHAT:
        links.append(
            InlineKeyboardButton(
                tr("group_onboarding.support"), url=f"https://t.me/{Config.SUPPORT_CHAT}"
            )
        )
    if Config.UPDATE_CHANNEL:
        links.append(
            InlineKeyboardButton(
                tr("group_onboarding.news"), url=f"https://t.me/{Config.UPDATE_CHANNEL}"
            )
        )
    if links:
        buttons.insert(1, links)
    if Config.SOURCE_URL:
        buttons.append([InlineKeyboardButton(tr("start.source_code"), url=Config.SOURCE_URL)])

    return (
        tr(
            "start.welcome",
            name=bot_name(client),
            url=start_pic_url or f"https://t.me/{bot_username(client)}",
        ),
        InlineKeyboardMarkup(buttons),
        photo,
    )


@command("start")
@leavemute
async def starttt(client, message):
    if len(message.text.split()) == 1:
        if message.chat.type == ChatType.PRIVATE:
            from Emilia.database.users import add_user

            current_bot_id = int(client.bot_token.split(":")[0])

            if getattr(client, "is_clone", False):
                await add_user(
                    message.from_user.id,
                    message.from_user.username,
                    bot_id=current_bot_id,
                )

            text, markup, photo = await build_start_message(client)

            if photo:
                try:
                    await message.reply_photo(photo, caption=text, reply_markup=markup)
                except (RPCError, OSError):
                    await message.reply_text(
                        text,
                        reply_markup=markup,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
            else:
                await message.reply_text(
                    text,
                    reply_markup=markup,
                    link_preview_options=LinkPreviewOptions(is_disabled=False),
                )

        else:
            from Emilia.database.users import add_chat

            if getattr(client, "is_clone", False):
                current_bot_id = int(client.bot_token.split(":")[0])
                await add_chat(message.chat.id, message.chat.title, bot_id=current_bot_id)

            await message.reply(tr("start.hey_there_ping_me_in_my_pm"))

    if len(message.text.split()) > 1:
        user = message.from_user.id
        chat = message.chat.id
        deep_cmd_list = (message.text.split()[1]).split("_")

        # Captcha
        if start_query_is(message, name="captcha"):
            await buttonCaptchaRedirect(client, message)
            await textCaptchaRedirect(client, message)

        # Private Notes
        elif start_query_is(message, name="note"):
            await note_redirect(client, message)

        # Connection
        elif start_query_is(message, name="connect"):
            await connectRedirect(client, message)

        elif start_query_is(message, name="onboard"):
            await onboarding_redirect(client, message, int(deep_cmd_list[1]))

        elif start_query_is(message, name="starter"):
            await starter_redirect(client, message, int(deep_cmd_list[1]))

        # Rules
        elif start_query_is(message, name="rules"):
            await rulesRedirect(message, client)

        # Shared playlist
        elif start_query_is(message, name="pl"):
            await playlist_redirect(client, message)

        # Content Request
        elif start_query_is(message, name="req"):
            await request_redirect(client, message)

        # Playlists menu deep-link (from Now Playing card "Playlists" button)
        elif start_query_is(message, name="playlists"):
            await playlist_menu_redirect(client, message)

        elif start_query_is(message, name="anihelp"):
            await anime_help(client, message)

        elif start_query_is(message, name="auth"):
            await auth_link_cmd(client, message)

        elif start_query_is(message, name="logout"):
            await logout_cmd(client, message)

        elif deep_cmd_list[0] == "des":
            try:
                req = deep_cmd_list[3]
            except IndexError:
                req = "desc"
            pic, result = await get_additional_info(deep_cmd_list[2], deep_cmd_list[1], req)
            await client.send_photo(chat, pic)
            try:
                await client.send_message(chat, result.replace("~!", "").replace("!~", ""))
            except (TypeError, AttributeError):
                await client.send_message(chat, tr("anime.no_description_available"))

        elif deep_cmd_list[0] == "anime":
            auth = False
            if await AUTH_USERS.find_one({"id": user}):
                auth = True
            result = await get_anime(
                {"id": int(deep_cmd_list[1])}, user=user, auth=auth, client=client
            )
            if error := anime_error(result):
                return await client.send_message(chat, error)
            pic, msg = result[0], result[1]
            buttons = await get_btns("ANIME", result=result, user=user, auth=auth, client=client)
            sent = await client.send_photo(chat, pic, caption=msg, reply_markup=buttons)
            await remember_menu(sent, user, client=client)

        elif deep_cmd_list[0] == "anirec":
            result = await get_recommendations(deep_cmd_list[1], client=client)
            await client.send_message(
                user, result, link_preview_options=LinkPreviewOptions(is_disabled=True)
            )


def start_query_is(message, name: str) -> bool:
    return message.text.split(maxsplit=1)[1].partition("_")[0] == name


button = [[InlineKeyboardButton(tr("start.clone_commands"), callback_data="bot_clone")]]


@callbackquery(
    filters=filters.regex("^(clone_help|bot_clone)$"), access=CallbackAccess(public=True)
)
async def callback_query_handler(client, callback_query):
    await callback_query.answer()
    if callback_query.data == "clone_help":
        await callback_query.message.reply_text(
            clone_help, reply_markup=InlineKeyboardMarkup(button)
        )
        await callback_query.message.delete()
        return
    if callback_query.data == "bot_clone":
        await callback_query.message.reply_text(
            help_text, link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        await callback_query.message.delete()
        return


clone_help = tr("clones.setup_guide")

help_text = tr("clones.hosting_notice")
