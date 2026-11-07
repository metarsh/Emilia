import re

from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton

from Emilia.utils.message_content import replace_range, text_value

BTN_URL_REGEX = re.compile(
    r"(\[([^\[]+?)\]\(buttonurl(?:#(primary|danger|success))?:(?:/{0,2})(.+?)(:same)?\))",
    flags=re.IGNORECASE,
)


def _normalize_button_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return url
    if re.match(r"(?i)^(https?://|tg://)", url):
        return url
    return f"https://{url}"


def button_markdown_parser(text):
    raw = text_value(text)
    buttons, edits = [], []
    for match in BTN_URL_REGEX.finditer(raw):
        preceding = match.start() - 1
        escapes = 0
        while preceding >= 0 and raw[preceding] == "\\":
            escapes += 1
            preceding -= 1
        if escapes % 2:
            edits.append((match.start() - 1, match.start()))
            continue
        button = InlineKeyboardButton(
            text=match.group(2),
            url=_normalize_button_url(match.group(4)),
            style=ButtonStyle(match.group(3).lower()) if match.group(3) else None,
        )
        if match.group(5) and buttons:
            buttons[-1].append(button)
        else:
            buttons.append([button])
        edits.append((match.start(), match.end()))
    for start, end in reversed(edits):
        text = replace_range(text, start, end, "")
    return text if text is not None else "", buttons
