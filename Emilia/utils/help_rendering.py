import html
import re

from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardMarkup, InputRichMessage, ReplyParameters

from Emilia.config import Config
from Emilia.utils.client_context import bot_name

SECTION = re.compile(r"^(?:\*\*([^*]+?):\*\*|#{2,6} (.+))$")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
SYNTAX_KEY = "Replace `<...>` with required input; `[...]` is optional. Do not type those brackets."


def _lines_outside_code(text: str):
    """Keep example code opaque when recognising the shared guide structure."""
    fence = ""
    for line in text.splitlines():
        marker = FENCE.match(line)
        if marker:
            if not fence:
                fence = marker[1]
            elif (
                marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip()
            ):
                fence = ""
            yield line, False
        else:
            yield line, not fence


def _sections(text: str):
    title, lines = "", []
    for line, outside_code in _lines_outside_code(text):
        heading = SECTION.fullmatch(line) if outside_code else None
        if heading:
            yield title, "\n".join(lines).strip()
            title, lines = heading[1] or heading[2], []
        else:
            lines.append(line)
    yield title, "\n".join(lines).strip()


def _example_preview(text: str):
    """Keep quick examples visible, with the rest available in a native disclosure."""
    lines = list(_lines_outside_code(text))
    starts = [
        index for index, (line, outside) in enumerate(lines) if outside and line.startswith("- ")
    ]
    if len(starts) <= 3:
        return text
    # Closing prose can contain important behaviour notes; leave it outside the disclosure.
    end = len(lines)
    for index in range(starts[-1] + 1, len(lines)):
        line, outside = lines[index]
        if outside and line and not line.startswith(" ") and not line.startswith("- "):
            end = index
            break

    def join(chunk):
        return "\n".join(line for line, _ in chunk).strip()

    return (
        f"{join(lines[: starts[2]])}\n\n"
        f"<details><summary>More examples</summary>\n\n"
        f"{join(lines[starts[2] : end])}\n\n</details>\n\n{join(lines[end:])}"
    ).strip()


def _section_content(title: str, text: str, *, compact: bool):
    name = title.casefold()
    if compact and name in {"example", "examples"}:
        text = _example_preview(text)
    elif name in {"tips", "setup tips"} and len(text) > 450:
        return f"<details><summary>{html.escape(title)}</summary>\n\n{text}\n\n</details>"
    return f"**{title}:**\n\n{text}"


def _guide_body(page):
    sections = []
    # A renamed menu label can leave the Markdown's original title in the loaded body.
    content = re.sub(r"\A# [^\n]+\n*", "", page.content)
    for title, text in _sections(content):
        formatted = []
        for line, outside in _lines_outside_code(text):
            if outside and line == SYNTAX_KEY:
                key = re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(line))
                formatted.append(f"<footer>{key}</footer>")
            else:
                formatted.append(line)
        text = "\n".join(formatted)
        if not title and page.id != "help" and not page.hidden:
            intro, separator, rest = text.partition("\n\n")
            if intro and not intro.startswith(("- ", "#", "<", "`")):
                text = "\n".join(f"> {line}" for line in intro.splitlines()) + separator + rest
        sections.append(_section_content(title, text, compact=not page.hidden) if title else text)
    return "\n\n".join(section for section in sections if section)


def _navigation_markup(keyboard, page):
    """Move supported help buttons into the message, retaining their callback routes."""
    if not isinstance(keyboard, InlineKeyboardMarkup):
        return ""
    rows = []
    for row_number, row in enumerate(keyboard.inline_keyboard):
        buttons = []
        for column, button in enumerate(row):
            if any(
                getattr(button, field, None) is not None
                for field in (
                    "web_app",
                    "login_url",
                    "switch_inline_query",
                    "switch_inline_query_current_chat",
                    "switch_inline_query_chosen_chat",
                    "copy_text",
                    "callback_game",
                    "pay",
                    "disabled",
                    "icon_custom_emoji_id",
                )
            ):
                return ""
            data = button.callback_data
            if isinstance(data, bytes):
                try:
                    data = data.decode("utf-8")
                except UnicodeDecodeError:
                    return ""
            if data is not None:
                action = f'type="callback_data" data="{html.escape(data, quote=True)}"'
            elif button.url:
                action = f'type="url" url="{html.escape(button.url, quote=True)}"'
            else:
                return ""
            style = getattr(button.style, "value", "default")
            if data and (
                data.startswith(("help:list:", "help:start", "hlplist_"))
                or (
                    data.startswith("help:page:")
                    and row_number == len(keyboard.inline_keyboard) - 1
                    and len(row) == 1
                )
            ):
                style = "default"
            elif (page.children and row_number == 0 and column == 0) or (
                data and data.startswith("help:page:bot:")
            ):
                style = "primary"
            appearance = (
                f' style="{style}"' if style in {"primary", "success", "danger", "link"} else ""
            )
            buttons.append(
                f"<tg-button {action}{appearance}>{html.escape(button.text)}</tg-button>"
            )
        if buttons:
            # Unset alignment uses Telegram's equal-width columns; left/center/right hug labels.
            rows.append("<tg-button-row>" + "\n".join(buttons) + "</tg-button-row>")
    if not rows:
        return ""
    return "\n\n<hr/>\n\n" + "\n\n".join(rows)


def _escape_markdown(value: str) -> str:
    value = " ".join(value.splitlines())
    return re.sub(r"([\\`*_\[\]()#|~!])", r"\\\1", html.escape(value, quote=False))


def help_markdown(client, page) -> str:
    contact = f"@{Config.SUPPORT_CHAT}" if Config.SUPPORT_CHAT else "the deployment operator"
    body = _guide_body(page).replace("{bot_name}", _escape_markdown(bot_name(client)))
    body = body.replace("{support_contact}", _escape_markdown(contact))
    return f"**{_escape_markdown(page.title)}**\n\n{body}"


async def show_help_page(client, message, page, keyboard, *, edit: bool = False):
    navigation = _navigation_markup(keyboard, page)
    rich = InputRichMessage(markdown=help_markdown(client, page) + navigation)
    reply_markup = None if navigation else keyboard
    try:
        if edit and (message.text or getattr(message, "rich_message", None)):
            return await client.edit_message_text(
                message.chat.id, message.id, rich_message=rich, reply_markup=reply_markup
            )
        return await client.send_rich_message(
            message.chat.id,
            rich_message=rich,
            reply_markup=reply_markup,
            reply_parameters=ReplyParameters(message_id=message.id),
            message_thread_id=getattr(message, "message_thread_id", None),
        )
    except MessageNotModified:
        return None
