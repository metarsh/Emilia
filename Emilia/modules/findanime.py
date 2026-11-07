from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.http import get
from Emilia.utils.uploader import upload

SAUCENAO_API_KEY = Config.SAUCENAO_API_KEY
SAUCENAO_API_URL = "https://saucenao.com/search.php"


async def search_image(image_url):
    if not SAUCENAO_API_KEY:
        raise RuntimeError("Configure SAUCENAO_API_KEY to enable image search")
    params = {
        "api_key": SAUCENAO_API_KEY,
        "url": image_url,
        "output_type": 2,  # JSON output
    }
    response = await get(SAUCENAO_API_URL, params=params)
    response.raise_for_status()
    return response.json()


def get_top_result(results):
    if not results:
        return None
    if not isinstance(results, list) or not isinstance(results[0], dict):
        raise ValueError("Invalid SauceNAO search results")
    data = results[0].get("data")
    urls = data.get("ext_urls") if isinstance(data, dict) else None
    if not isinstance(urls, list) or not urls:
        return None
    if not isinstance(urls[0], str):
        raise ValueError("Invalid SauceNAO result URL")
    return {"url": urls[0]}


@command("findanime", disable=True, rate_limit=Config.RATE_LIMIT_HEAVY)
async def saucenao_search(client, message):
    reply = message.reply_to_message
    if not reply:
        return await reply_usage(message)
    if not (reply.photo or reply.document):
        return await reply_usage(message)
    if reply.document and reply.document.mime_type.split("/")[0] != "image":
        return await reply_usage(message)
    url2 = await upload(reply)
    wait = await message.reply_text(tr("findanime.searching_for_the_image_on_saucenao"))

    results = await search_image(url2)
    top_result = get_top_result(results["results"])
    if top_result:
        await message.reply_text(tr("findanime.top_result", url=top_result["url"]))
    else:
        await message.reply_text(tr("findanime.no_results_found"))
    await wait.delete()
