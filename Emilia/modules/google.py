import hashlib
import html
import urllib.parse

from aiohttp import ClientError
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
)
from redis.exceptions import RedisError
from selectolax.lexbor import LexborHTMLParser

from Emilia.application import LOGGER
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.cache import SimpleCache
from Emilia.utils.command_help import reply_usage
from Emilia.utils.executors import run_in_thread
from Emilia.utils.http import get

SEARCH_CACHE = SimpleCache(60, "web_search", max_l1_entries=256)


def _parse_search_results(text: str, num_results: int) -> list:
    results = []
    seen = set()
    tree = LexborHTMLParser(text)
    if tree.css_first(".anomaly-modal, .anomaly-modal__mask, form[action*='anomaly']"):
        raise ValueError("The search provider requested verification. Please try again later.")
    for anchor in tree.css(".result .result__title a[href]"):
        if len(results) >= num_results:
            break
        title = " ".join(anchor.text(separator=" ").split())
        try:
            href = urllib.parse.urljoin("https://duckduckgo.com", anchor.attributes["href"])
            parsed = urllib.parse.urlsplit(href)
            if parsed.hostname in {"duckduckgo.com", "html.duckduckgo.com"}:
                target = urllib.parse.parse_qs(parsed.query).get("uddg")
                if target:
                    href = target[0]
                elif parsed.path == "/l/":
                    continue
            parsed = urllib.parse.urlsplit(href)
        except ValueError:
            continue
        if not title or parsed.scheme not in {"http", "https"} or not parsed.netloc:
            continue
        if href not in seen:
            results.append({"title": title, "url": href})
            seen.add(href)
    return results


async def fetch_duckduckgo(query: str, num_results: int = 10) -> list:
    if not isinstance(num_results, int) or isinstance(num_results, bool) or num_results < 0:
        raise ValueError("The search result limit must be a nonnegative integer")
    if num_results == 0:
        return []
    query = query.strip()
    if not query:
        return []

    async def load():
        response = await get(
            "https://html.duckduckgo.com/html/", params={"q": query}, max_bytes=2 * 1024**2
        )
        response.raise_for_status()
        return await run_in_thread(_parse_search_results, response.text, num_results)

    key = hashlib.sha256(f"{num_results}:{query}".encode()).hexdigest()
    return await SEARCH_CACHE.get_or_load(key, load)


@command(["google", "g"], disable=True)
async def google_search_cmd(client: Client, message):
    if len(message.command) < 2:
        return await reply_usage(message, google_search_cmd)

    query = message.text.split(None, 1)[1]
    wait_msg = await message.reply_text(tr("google.searching"))

    try:
        results = await fetch_duckduckgo(query, num_results=10)

        if not results:
            return await wait_msg.edit_text(tr("google.no_results_found_try_a_different_query"))

        response_text = tr("google.search_results", query=html.escape(query[:200]))

        for idx, res in enumerate(results, start=1):
            title = html.escape(res["title"][:160])
            url = html.escape(res["url"], quote=True)
            response_text += f'{idx}. <a href="{url}">{title}</a>\n'

        encoded_query = urllib.parse.quote_plus(query)
        google_url = f"https://www.google.com/search?q={encoded_query}"

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(tr("google.google"), url=google_url)]]
        )

        await wait_msg.edit_text(
            response_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )

    except (ClientError, RPCError, RedisError, OSError, ValueError):
        LOGGER.exception("Google search failed")
        await wait_msg.edit_text(tr("google.error_occurred"))
