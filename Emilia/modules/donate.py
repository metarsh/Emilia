from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr


@command("donate")
async def handle_donate(client, message):
    if not Config.DONATION_URL:
        return await message.reply_text(tr("donate.donations_are_not_configured_for_this_bot"))
    text = tr("donate.thank_supporting_bot_use_button_below_donate")
    button = InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr("donate.donate"), url=Config.DONATION_URL)]]
    )
    await message.reply_text(text, reply_markup=button)
