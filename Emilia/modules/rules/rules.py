from pyrogram.enums import ChatType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.custom_filter import command
from Emilia.database.rules import get_private_note, get_rules, get_rules_button
from Emilia.locales import tr
from Emilia.utils.button_gen import (
    button_markdown_parser,
)
from Emilia.utils.chat_context import bind_target, effective_chat, effective_chat_id
from Emilia.utils.client_context import bot_username
from Emilia.utils.message_content import prefix_content
from Emilia.utils.note_format import NoteFillings as rules_filler
from Emilia.utils.saved_message import send_saved_message


@command("rules", disable=True, allow_connected=True, chat_scope="group")
async def rules(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if effective_chat(message).type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return await message.reply(tr("errors.group_only"))

    rules_text = await get_rules(chat_id)
    if rules_text is None:
        return await message.reply(
            tr("rules.this_chat_doesn_t_seem_to_have"),
        )

    if not (await get_private_note(chat_id)):
        rules_text, buttons = button_markdown_parser(rules_text)
        button_markdown = None
        if len(buttons) > 0:
            button_markdown = InlineKeyboardMarkup(buttons)

        rules_text = rules_filler(message, rules_text)

        await send_saved_message(
            client,
            message.chat.id,
            None,
            prefix_content(rules_text, f"Rules for {chat_title}:\n\n"),
            1,
            reply_markup=button_markdown,
            reply_message_id=message.id,
        )

    else:
        button_text = await get_rules_button(chat_id)
        button = [
            [
                InlineKeyboardButton(
                    text=button_text,
                    url=f"https://t.me/{bot_username(client)}?start=rules_{chat_id}",
                )
            ]
        ]

        await message.reply(
            tr("rules.click_on_the_button_to_see_the"),
            reply_markup=InlineKeyboardMarkup(button),
        )


async def rulesRedirect(message, client):
    chat_id = int(message.text.split()[1].split("_")[1])
    chat = await client.get_chat(chat_id)
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return await message.reply_text(tr("errors.group_only"))
    bind_target(message, chat)
    chat_title = chat.title
    rules_text = await get_rules(chat_id)

    if rules_text is None:
        return await message.reply(tr("rules.this_chat_doesn_t_seem_to_have"))
    rules_text, buttons = button_markdown_parser(rules_text)
    button_markdown = None
    if len(buttons) > 0:
        button_markdown = InlineKeyboardMarkup(buttons)

    rules_text = rules_filler(message, rules_text)
    await send_saved_message(
        client,
        message.chat.id,
        None,
        prefix_content(rules_text, f"Rules for {chat_title}:\n\n"),
        1,
        reply_markup=button_markdown,
        reply_message_id=message.id,
    )
