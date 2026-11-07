import html
import re

from pyrogram.errors import MessageNotModified
from pyrogram.types import InputRichMessage, ReplyParameters

from Emilia.config import Config
from Emilia.utils.client_context import bot_name


def _escape_markdown(value: str) -> str:
    value = " ".join(value.splitlines())
    return re.sub(r"([\\`*_\[\]()#|~!])", r"\\\1", html.escape(value, quote=False))


def help_markdown(client, page) -> str:
    contact = f"@{Config.SUPPORT_CHAT}" if Config.SUPPORT_CHAT else "the deployment operator"
    body = page.content.replace("{bot_name}", _escape_markdown(bot_name(client)))
    body = body.replace("{support_contact}", _escape_markdown(contact))
    return f"# {_escape_markdown(page.title)}\n\n{body}"


async def show_help_page(client, message, page, keyboard, *, edit: bool = False):
    rich = InputRichMessage(markdown=help_markdown(client, page))
    try:
        if edit and (message.text or getattr(message, "rich_message", None)):
            return await client.edit_message_text(
                message.chat.id, message.id, rich_message=rich, reply_markup=keyboard
            )
        return await client.send_rich_message(
            message.chat.id,
            rich_message=rich,
            reply_markup=keyboard,
            reply_parameters=ReplyParameters(message_id=message.id),
            message_thread_id=getattr(message, "message_thread_id", None),
        )
    except MessageNotModified:
        return None
