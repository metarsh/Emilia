from pyrogram.enums import ParseMode
from pyrogram.errors import BadRequest, MessageNotModified
from pyrogram.types import InputRichMessage, LinkPreviewOptions

from Emilia.application import LOGGER
from Emilia.custom_filter import auth
from Emilia.locales import tr
from Emilia.utils.deployment_stats import build_dashboard, plain_chunks


@auth(pattern="stats|devstats")
async def devstats(client, message):
    status = await message.reply_text(tr("devstats.gathering_stats"))
    rich, plain = await build_dashboard()
    try:
        await status.edit_text(rich_message=InputRichMessage(html=rich))
    except MessageNotModified:
        return
    except BadRequest as error:
        LOGGER.warning("Stats rich rendering unavailable: %s", type(error).__name__)
        chunks = iter(plain_chunks(plain))
        options = {
            "parse_mode": ParseMode.DISABLED,
            "link_preview_options": LinkPreviewOptions(is_disabled=True),
        }
        await status.edit_text(next(chunks), **options)
        for chunk in chunks:
            await message.reply_text(chunk, **options)
