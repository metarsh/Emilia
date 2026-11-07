from pyrogram.enums import ChatType
from pyrogram.errors import ReplyMessageIdInvalid
from pyrogram.types import ReplyParameters

from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.database.nsfw import is_nsfw_on, nsfw_off, nsfw_on
from Emilia.locales import tr
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.get_user import mention_html
from Emilia.utils.http import get
from Emilia.utils.message_actor import actor_id, actor_name, sender_entity

url_nsfw = "https://api.purrbot.site/v2/img/nsfw"
_HEADERS = {"User-Agent": Config.HTTP_USER_AGENT}


async def send_nsfw_media(client, message, img, caption=None):
    reply_id = getattr(message.reply_to_message, "id", None)
    reply_parameters = ReplyParameters(message_id=reply_id) if reply_id else None

    from pyrogram.enums import ParseMode

    try:
        if str(img).lower().split("?")[0].endswith(".gif"):
            return await client.send_animation(
                message.chat.id,
                img,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_parameters=reply_parameters,
            )
        return await client.send_photo(
            message.chat.id,
            img,
            caption=caption,
            parse_mode=ParseMode.HTML,
            reply_parameters=reply_parameters,
        )
    except ReplyMessageIdInvalid:
        if str(img).lower().split("?")[0].endswith(".gif"):
            return await client.send_animation(
                message.chat.id, img, caption=caption, parse_mode=ParseMode.HTML
            )
        return await client.send_photo(
            message.chat.id, img, caption=caption, parse_mode=ParseMode.HTML
        )


@command("addnsfw")
@anonadmin_checker
@log_to_channel
async def add_nsfw(client, message):
    if not await is_user_admin(message, user_id=actor_id(message), silent=False):
        return

    is_nsfw = await is_nsfw_on(message.chat.id)
    if not is_nsfw:
        await nsfw_on(message.chat.id)
        await message.reply_text(tr("nsfw.activated_nsfw_mode"))
        return "NSFW_ACTIVE", None, None
    else:
        return await message.reply_text(tr("nsfw.nsfw_mode_is_already_activated_for_this"))


@command("rmnsfw")
@anonadmin_checker
@log_to_channel
async def rem_nsfw(client, message):
    if not await is_user_admin(message, user_id=actor_id(message), silent=False):
        return

    is_nsfw = await is_nsfw_on(message.chat.id)
    if not is_nsfw:
        return await message.reply_text(tr("nsfw.nsfw_mode_is_already_deactivated"))
    else:
        await nsfw_off(message.chat.id)
        await message.reply_text(tr("nsfw.rolled_back_to_sfw_mode"))
        return "NSFW_DEACTIVE", None, None


async def send_nsfw_category(client, message, category, kind="gif", action_name=None):
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        is_nsfw = await is_nsfw_on(message.chat.id)
        if not is_nsfw:
            return await message.reply_text(tr("nsfw.disabled"))

    result = await get(f"{url_nsfw}/{category}/{kind}", headers=_HEADERS)
    try:
        result.raise_for_status()
        result_json = result.json() or {}
    except ValueError:
        return
    if result_json.get("error"):
        return
    img = result_json.get("link")
    if not img:
        return

    caption = ""
    if action_name and message.reply_to_message and sender_entity(message.reply_to_message):
        user_a = mention_html(actor_id(message), actor_name(message), client=client)
        user_b = mention_html(
            actor_id(message.reply_to_message),
            actor_name(message.reply_to_message),
            client=client,
        )
        caption = tr(
            "nsfw.send_nsfw_category_user_a_action_name_user_b",
            user_a=user_a,
            action_name=action_name,
            user_b=user_b,
        )
    elif action_name:
        user_a = mention_html(actor_id(message), actor_name(message), client=client)
        caption = tr(
            "nsfw.send_nsfw_category_user_a_action_name", user_a=user_a, action_name=action_name
        )

    await send_nsfw_media(client, message, img, caption=caption if caption else None)


def _register_nsfw(pattern, category, kind="gif"):
    @command(pattern=pattern, rate_limit=Config.RATE_LIMIT_HEAVY)
    async def handler(client, message):
        action_name = pattern.split("|")[0].replace("(", "").replace(")", "")
        await send_nsfw_category(client, message, category, kind, action_name)

    return handler


blowjob = _register_nsfw("blowjob|bj", "blowjob")
anal = _register_nsfw("anal", "anal")
cum = _register_nsfw("cum", "cum")
fuck = _register_nsfw("fuck", "fuck")
nsfwneko = _register_nsfw("(nsfwneko|nneko)", "neko", "gif")
pussylick = _register_nsfw("pussylick", "pussylick")
solo = _register_nsfw("solo", "solo")
solomale = _register_nsfw("solomale", "solo_male")
threesomefff = _register_nsfw("threesomefff", "threesome_fff")
threesomeffm = _register_nsfw("threesomeffm", "threesome_ffm")
threesomemmf = _register_nsfw("threesomemmf", "threesome_mmf")
yaoi = _register_nsfw("yaoi", "yaoi")
yuri = _register_nsfw("yuri", "yuri")
