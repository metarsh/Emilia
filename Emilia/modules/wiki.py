import asyncio
import io
from html import escape

import wikipedia
from pyrogram.enums import ParseMode
from pyrogram.types import LinkPreviewOptions
from requests.exceptions import RequestException
from wikipedia.exceptions import DisambiguationError, PageError, WikipediaException

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage


def _wikipedia_summary_sync(search):
    return wikipedia.page(search).summary


async def get_wikipedia_summary(search):
    # wikipedia lib is fully synchronous (urllib under the hood); keep it
    # off the event loop.
    return await asyncio.to_thread(_wikipedia_summary_sync, search)


@command("wiki", disable=True, rate_limit=Config.RATE_LIMIT_HEAVY)
async def wiki(client, message):
    if message.reply_to_message:
        search_query = (message.reply_to_message.text or "").strip()
    else:
        input_args = (message.text or "").split(None, 1)
        if len(input_args) < 2:
            await reply_usage(message)
            return
        search_query = input_args[1].strip()

    try:
        wikipedia.set_lang("en")
        wikipedia.set_rate_limiting(True)
        summary = await get_wikipedia_summary(search_query)
        result = f"<b>{escape(search_query)}</b>\n\n"
        result += f"<i>{escape(summary)}</i>\n"
        result += tr("wiki.read_more", search_query=search_query.replace(" ", "%20"))
    except DisambiguationError as e:
        result = tr("wiki.disambiguated_pages_found_adjust_query_accordingly", suggestions=e)
    except PageError as e:
        result = f"<code>{escape(str(e))}</code>"
    except (RequestException, WikipediaException) as e:
        LOGGER.error(f"Error: {e}")
        result = tr("wiki.error_occurred_while_processing_request")

    if len(result) > 4000:
        with io.BytesIO(result.encode("utf-8")) as document:
            document.name = "wikipedia.txt"
            await client.send_document(message.chat.id, document)
    else:
        await message.reply_text(
            result,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
