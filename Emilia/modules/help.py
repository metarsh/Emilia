from pyrogram import filters
from pyrogram.enums import ButtonStyle, ChatType
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, LinkPreviewOptions

from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.locales.help import HELP_PAGES, HelpPage
from Emilia.utils.client_context import bot_username
from Emilia.utils.help_rendering import show_help_page
from Emilia.utils.menu_guard import CallbackAccess

HELP_TEXT = tr("help.index")
HELP_INDEX = HelpPage("help", "Help", HELP_TEXT)
PAGE_SIZE = 24


def _find_page(name: str):
    return HELP_PAGES.get(name) or next(
        (page for page in HELP_PAGES.values() if page.title.casefold() == name.casefold()), None
    )


def _index_keyboard(page_number: int = 0):
    pages = sorted((page for page in HELP_PAGES.values() if not page.hidden), key=lambda p: p.title)
    total = max(1, (len(pages) + PAGE_SIZE - 1) // PAGE_SIZE)
    number = max(0, min(page_number, total - 1))
    buttons = [
        InlineKeyboardButton(page.title, callback_data=f"help:page:{page.id}")
        for page in pages[number * PAGE_SIZE : (number + 1) * PAGE_SIZE]
    ]
    rows = [buttons[index : index + 3] for index in range(0, len(buttons), 3)]
    navigation = []
    if total > 1:
        navigation.append(
            InlineKeyboardButton("《", callback_data=f"help:list:{(number - 1) % total}")
        )
    navigation.append(
        InlineKeyboardButton(
            tr("buttons.back"), callback_data="help:start", style=ButtonStyle.PRIMARY
        )
    )
    if total > 1:
        navigation.append(
            InlineKeyboardButton("》", callback_data=f"help:list:{(number + 1) % total}")
        )
    return InlineKeyboardMarkup([*rows, navigation])


def _page_content(client, page, parent: str | None = None):
    buttons = [
        InlineKeyboardButton(HELP_PAGES[child].title, callback_data=f"help:page:{child}:{page.id}")
        for child in page.children
    ]
    rows = [buttons[index : index + 2] for index in range(0, len(buttons), 2)]
    back = f"help:page:{parent}" if parent in HELP_PAGES else "help:list:0"
    rows.append(
        [InlineKeyboardButton(tr("buttons.back"), callback_data=back, style=ButtonStyle.PRIMARY)]
    )
    return InlineKeyboardMarkup(rows)


async def _show_start(message, text: str, keyboard, *, edit: bool = False):
    options = {
        "reply_markup": keyboard,
        "link_preview_options": LinkPreviewOptions(is_disabled=True),
    }
    # The start screen uses its existing message format.
    if edit and (message.text or getattr(message, "rich_message", None)):
        await message.edit_text(text, **options)
    else:
        await message.reply_text(text, **options)


async def module_page(client, module: str, message, edit: bool = False, parent: str | None = None):
    page = _find_page(module)
    if page:
        await show_help_page(client, message, page, _page_content(client, page, parent), edit=edit)
    else:
        await show_help_page(client, message, HELP_INDEX, _index_keyboard(), edit=edit)


@command("help", disable=True)
async def help_command(client, message):
    arguments = message.text.split(maxsplit=1)
    page = _find_page(arguments[1].strip().lower()) if len(arguments) > 1 else None
    if message.chat.type == ChatType.PRIVATE:
        await module_page(client, page.id if page else "", message)
        return
    slug = page.id if page else ""
    redirect = HelpPage(
        "help",
        "Help",
        tr("help.module_redirect", module_name=page.title) if page else tr("help.private_redirect"),
    )
    await show_help_page(
        client,
        message,
        redirect,
        InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("help.open_module") if page else tr("help.open_private"),
                        url=f"https://t.me/{bot_username(client)}?start=help_{slug}",
                    )
                ]
            ]
        ),
    )


@command("start", group=9)
async def help_redirect(client, message):
    arguments = message.text.split(maxsplit=1)
    if len(arguments) > 1 and arguments[1].startswith("help_"):
        await module_page(client, arguments[1].removeprefix("help_"), message)


@callbackquery(filters=filters.regex("^help:"), access=CallbackAccess(public=True))
async def help_button(client, query):
    parts = query.data.split(":")
    action = parts[1]
    try:
        if action == "start":
            from Emilia.modules.start.start import build_start_message

            text, keyboard, _ = await build_start_message(client)
            await _show_start(query.message, text, keyboard, edit=True)
        elif action == "list" and len(parts) == 3 and parts[2].isdigit():
            await show_help_page(
                client, query.message, HELP_INDEX, _index_keyboard(int(parts[2])), edit=True
            )
        elif action == "page" and len(parts) in {3, 4}:
            await module_page(
                client,
                parts[2],
                query.message,
                edit=True,
                parent=parts[3] if len(parts) == 4 else None,
            )
    except MessageNotModified:
        pass
    await query.answer()
