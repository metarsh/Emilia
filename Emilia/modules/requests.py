import asyncio
import html
import re
from typing import Any

from pymongo.errors import PyMongoError
from pyrogram import Client, filters
from pyrogram.enums import ChatType, ParseMode
from pyrogram.errors import FloodWait, PeerIdInvalid, RPCError, UserIsBlocked
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from redis.exceptions import RedisError

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command
from Emilia.database import requests as rdb
from Emilia.locales import tr
from Emilia.utils.channels import channel_destination
from Emilia.utils.chat_context import effective_chat_id
from Emilia.utils.chat_status import has_chat_permission, is_user_admin, permission_denied
from Emilia.utils.client_context import bot_username
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.errors import report_error, telegram_error_text
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_user
from Emilia.utils.tasks import spawn

G_VIEW, G_OPEN, G_ADD, G_DONE, G_REJECT, G_PENDING, G_BULLET, G_SUB = (
    "▷",
    "⇱",
    "＋",
    "✓",
    "✕",
    "◷",
    "•",
    "›",
)

SEARCH_SEMAPHORE = asyncio.Semaphore(50)
_BROADCAST_SEMAPHORE = asyncio.Semaphore(10)
_MAX_FLOOD_SLEEP = 30


def _clean_markdown(text: str) -> str:
    if not text:
        return ""
    sanitized = re.sub(r"[\[\]`*_]", " ", str(text))
    return " ".join(sanitized.split()).strip()


async def _search_channels(
    client: Client, channels: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    async def _search_one(ch: dict[str, Any]):
        cid = ch.get("id")
        title = _clean_markdown(ch.get("title", "Channel"))
        if not cid:
            return

        async with SEARCH_SEMAPHORE:
            try:
                channel = await client.get_chat(cid)
                if channel.type != ChatType.CHANNEL:
                    return
                async for msg in client.search_messages(chat_id=channel.id, query=query, limit=4):
                    if not msg.link:
                        continue
                    media = msg.document or msg.video or msg.audio or msg.photo or msg.animation
                    fname = getattr(media, "file_name", None) or getattr(media, "title", None)
                    if not fname:
                        fname = (msg.caption or msg.text or f"Post #{msg.id}").split("\n")[0][:50]
                    cleaned_name = _clean_markdown(fname) or f"Post #{msg.id}"
                    results.append({"name": cleaned_name, "title": title, "url": msg.link})
            except (RPCError, OSError) as e:
                LOGGER.debug(f"Channel search failed for {cid}: {e}")

    await asyncio.gather(*[_search_one(c) for c in channels], return_exceptions=True)
    return results


def _render_search_results(
    query: str, results: list[dict[str, Any]]
) -> tuple[str, InlineKeyboardMarkup]:
    clean_q = _clean_markdown(query)
    lines = [tr("requests.search_results_found_matches", results=len(results), clean_q=clean_q)]
    buttons: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for idx, item in enumerate(results[:6], 1):
        lines.append(
            tr(
                "requests.open",
                g_bullet=G_BULLET,
                idx=idx,
                name=item["name"],
                g_sub=G_SUB,
                g_view=G_VIEW,
                title=item["title"],
                url=item["url"],
            )
        )
        row.append(
            InlineKeyboardButton(tr("requests.post", g_view=G_VIEW, idx=idx), url=item["url"])
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return "\n".join(lines), InlineKeyboardMarkup(buttons)


def _render_req_card(
    doc: dict[str, Any], is_admin: bool = False, *, client=None
) -> tuple[str, InlineKeyboardMarkup | None]:
    num, query, status = doc["num"], _clean_markdown(doc["query"]), doc.get("status", "pending")
    subs = len(doc.get("subscribers", []))
    req_id = f"req_{doc['num']}"

    if is_admin:
        stat_label = (
            f"{G_DONE} Uploaded"
            if status == "completed"
            else f"{G_REJECT} Rejected"
            if status == "rejected"
            else f"{G_PENDING} Pending ({subs})"
        )
        text = tr(
            "requests.content_request_req_query_status",
            num=num,
            g_bullet=G_BULLET,
            query=query,
            g_bullet_2=G_BULLET,
            stat_label=stat_label,
        )
        if doc.get("post_url"):
            text += tr(
                "requests.post_view_uploaded_file", g_bullet=G_BULLET, post_url=doc["post_url"]
            )
        if status == "pending":
            markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("requests.done", g_done=G_DONE),
                            callback_data=f"req:done:{req_id}",
                        ),
                        InlineKeyboardButton(
                            tr("requests.reject", g_reject=G_REJECT),
                            callback_data=f"req:reject:{req_id}",
                        ),
                    ]
                ]
            )
            return text, markup
        return text, None

    text = tr(
        "requests.no_matches_found_request_req_queued_uploaders_status",
        query=query,
        num=num,
        g_bullet=G_BULLET,
        g_pending=G_PENDING,
        g_bullet_2=G_BULLET,
        subs=subs,
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("requests.subscribe_button", g_add=G_ADD, subs=subs),
                    callback_data=f"req:metoo:{req_id}",
                ),
                InlineKeyboardButton(
                    tr("requests.enable_pm_alerts", g_open=G_OPEN),
                    url=f"https://t.me/{bot_username(client)}?start={req_id}",
                ),
            ]
        ]
    )
    return text, markup


async def _safe_send_pm(
    client: Client, user_id: int, text: str, markup: InlineKeyboardMarkup | None
):
    try:
        await client.send_message(
            user_id,
            text,
            reply_markup=markup,
            link_preview_options=LinkPreviewOptions(is_disabled=False),
        )
    except FloodWait as e:
        if e.value > _MAX_FLOOD_SLEEP:
            LOGGER.warning("[Requests] FloodWait %ds for PM to %s — skipping", e.value, user_id)
            return
        await asyncio.sleep(e.value)
        try:
            await client.send_message(
                user_id,
                text,
                reply_markup=markup,
                link_preview_options=LinkPreviewOptions(is_disabled=False),
            )
        except (RPCError, OSError):
            pass
    except (UserIsBlocked, PeerIdInvalid, RPCError):
        pass


def _broadcast_update(client: Client, doc: dict[str, Any]):
    num, query, status = doc["num"], _clean_markdown(doc["query"]), doc.get("status")
    post_url, reason = doc.get("post_url"), doc.get("reason")

    if status == "completed":
        if post_url:
            text = tr(
                "requests.request_completed_req_now_available_open_post_channel",
                num=num,
                query=query,
                g_sub=G_SUB,
                post_url=post_url,
            )
            markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(tr("requests.open_post", g_view=G_VIEW), url=post_url)]]
            )
        else:
            text = tr(
                "requests.request_completed_req_has_uploaded_channel_admins", num=num, query=query
            )
            markup = None
    else:
        text = tr(
            "requests.request_rejected_req_rejected_reason",
            num=num,
            query=query,
            g_bullet=G_BULLET,
            reason=_clean_markdown(reason or "Unavailable"),
        )
        markup = None

    subscribers = doc.get("subscribers") or []

    async def _runner():
        recipients = iter(subscribers)

        async def worker():
            for uid in recipients:
                async with _BROADCAST_SEMAPHORE:
                    await _safe_send_pm(client, uid, text, markup)

        await asyncio.gather(*(worker() for _ in range(min(10, len(subscribers)))))

    return spawn(_runner(), name=f"request_broadcast:{doc['_id']}")


async def _check_admin(message: Message) -> int | None:
    cid = effective_chat_id(message)
    if not await is_user_admin(message, chat_id=cid, silent=False):
        return None
    return cid


async def request_redirect(client: Client, message: Message):
    raw_id = message.text.split()[1].replace("req_", "").replace("req-", "").strip()
    if not raw_id:
        await message.reply(tr("requests.invalid_request_link_no_request_id_provided"))
        return
    doc = await rdb.get_request(raw_id)
    if not doc:
        await message.reply(tr("requests.no_request_found_id", raw_id=raw_id))
        return
    user = actor_user(message)
    if user is not None:
        await rdb.add_subscriber(doc["num"], user.id)
    clean_q = _clean_markdown(doc["query"])
    text = tr(
        "requests.subscribed_pm_alerts_req_content_status_will_receive",
        num=doc["num"],
        g_bullet=G_BULLET,
        clean_q=clean_q,
        g_bullet_2=G_BULLET,
        g_pending=G_PENDING if doc["status"] == "pending" else G_DONE,
        status=doc["status"].title(),
    )
    markup = (
        InlineKeyboardMarkup(
            [[InlineKeyboardButton(tr("requests.view_post", g_view=G_VIEW), url=doc["post_url"])]]
        )
        if doc.get("post_url")
        else None
    )
    await message.reply(text, reply_markup=markup)


async def _handle_req(client: Client, message: Message, query: str):
    user = actor_user(message)
    clean_q = query.strip()[:120]
    if not user or not clean_q:
        return

    chat_id = effective_chat_id(message)

    settings = await rdb.get_settings(chat_id)
    if not settings.get("is_enabled", True):
        await message.reply(tr("requests.disabled"))
        return

    channels = settings.get("channels", [])
    req_ch = settings.get("req_channel")

    if not channels and not req_ch:
        await message.reply(tr("requests.configuration_required"))
        return

    if channels:
        matches = await _search_channels(client, channels, clean_q)
        if matches:
            text, markup = _render_search_results(clean_q, matches)
            await message.reply(
                text, reply_markup=markup, link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
            return

    if not req_ch:
        await message.reply(
            tr(
                "requests.no_matches_found",
                clean_q=_clean_markdown(clean_q),
                req_channel_not_set=tr("requests.channel_not_set"),
            )
        )
        return

    existing = await rdb.find_active_request(clean_q, chat_id=chat_id)
    if existing:
        await rdb.add_subscriber(existing["num"], user.id)
        doc = await rdb.get_request(existing["num"]) or existing
        text, markup = _render_req_card(doc, client=client)
        await message.reply(
            tr("requests.request_already_active_req_added_subscribers", num=doc["num"]),
            reply_markup=markup,
        )
        return

    max_limit = int(settings.get("daily_limit", 0))
    allowed, _ = await rdb.check_and_increment_daily_limit(chat_id, user.id, max_limit)
    if not allowed:
        await message.reply(tr("requests.daily_limit_reached").format(max_limit))
        return

    doc = await rdb.create_request(
        chat_id, user.id, user.first_name or "User", clean_q, req_channel=req_ch
    )
    if doc.pop("_existing", False):
        _, markup = _render_req_card(doc, client=client)
        return await message.reply(
            tr("requests.request_already_active_req_added_subscribers", num=doc["num"]),
            reply_markup=markup,
        )
    try:
        adm_text, adm_markup = _render_req_card(doc, is_admin=True, client=client)
        await client.send_message(
            req_ch,
            adm_text,
            reply_markup=adm_markup,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except (RPCError, OSError) as e:
        LOGGER.warning(f"Failed to post to request channel {req_ch}: {e}")
        await report_error(
            "requests.post_card", e, chat_id=chat_id, req_channel=req_ch, req_id=doc.get("_id")
        )

    user_text, user_markup = _render_req_card(doc, client=client)
    await message.reply(user_text, reply_markup=user_markup)


@command(["req", "request", "searchreq"], disable=True, allow_connected=True, chat_scope="group")
async def req_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        reply = message.reply_to_message
        query = (reply.text or reply.caption) if reply else None
        if not query:
            await reply_usage(message)
            return
    else:
        query = message.text.split(None, 1)[1]
    await _handle_req(client, message, query)


@command(["req", "request"], prefixes="#", disable=True, allow_connected=True, chat_scope="group")
async def req_hashtag(client: Client, message: Message):
    match = message.matches[0] if message.matches else None
    query = match.group(1) if match else None
    if not query:
        reply = message.reply_to_message
        query = (reply.text or reply.caption) if reply else None
    if query:
        await _handle_req(client, message, query.strip())


@command(["reqs", "myrequests", "requests"], disable=True)
async def my_reqs_cmd(client: Client, message: Message):
    user = actor_user(message)
    if user is None:
        return
    reqs = await rdb.get_user_requests(user.id)
    if not reqs:
        await message.reply(tr("requests.my_requests_you_have_no_active_or"))
        return
    lines = [tr("requests.requests")]
    for r in reqs:
        icon = (
            G_DONE
            if r.get("status") == "completed"
            else G_REJECT
            if r.get("status") == "rejected"
            else G_PENDING
        )
        link = f" › [Post]({r['post_url']})" if r.get("post_url") else ""
        clean_q = _clean_markdown(r.get("query", ""))
        lines.append(
            f"{G_BULLET} `#REQ-{r['num']}` `{icon} {r['status'].title()}`: **{clean_q}**{link}"
        )
    await message.reply("\n".join(lines), link_preview_options=LinkPreviewOptions(is_disabled=True))


@command(["reqstatus", "requeststatus"], disable=True)
async def req_status_cmd(client: Client, message: Message):
    if len(message.command) < 2:
        await reply_usage(message)
        return
    raw_id = message.command[1]
    doc = await rdb.get_request(raw_id)
    if not doc:
        await message.reply(tr("requests.no_request_found_id", raw_id=raw_id))
        return
    clean_q = _clean_markdown(doc["query"])
    text = tr(
        "requests.request_status_req_query_status",
        num=doc["num"],
        g_bullet=G_BULLET,
        clean_q=clean_q,
        g_bullet_2=G_BULLET,
        status=doc["status"].title(),
    )
    if doc.get("post_url"):
        text += tr("requests.link_open_file", g_bullet=G_BULLET, post_url=doc["post_url"])
    await message.reply(text, link_preview_options=LinkPreviewOptions(is_disabled=True))


@command(
    ["setreq", "setrequest", "setreqchannel"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group",
)
@anonadmin_checker(named=True)
async def set_req_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await reply_usage(message)
        return
    try:
        target = await channel_destination(client, message, message.command[1], posting=True)
        if target is None:
            return
        await rdb.update_settings(cid, {"req_channel": target.id, "req_title": target.title})
        await message.reply(
            tr(
                "requests.set_request_channel",
                title=html.escape(target.title or "Channel"),
                set=target.id,
            ),
            parse_mode=ParseMode.HTML,
        )
    except (RPCError, PyMongoError, RedisError, OSError) as exc:
        LOGGER.exception("Request channel configuration failed for chat %s", cid)
        await message.reply(telegram_error_text(exc) or tr("requests.could_not_access_channel"))


@command(
    ["unsetreq", "unsetrequest"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group",
)
@anonadmin_checker
async def unset_req_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    await rdb.update_settings(cid, {"req_channel": None, "req_title": None})
    await message.reply(tr("requests.request_channel_disconnected"))


@command(
    ["addchannel", "addcontentchannel"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group",
)
@anonadmin_checker(named=True)
async def add_channel_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await reply_usage(message)
        return
    try:
        target = await channel_destination(client, message, message.command[1])
        if target is None:
            return
        await rdb.add_channel(cid, target.id, target.title or "Channel", target.username)
        await message.reply(
            tr(
                "requests.added_search_pool",
                title=html.escape(target.title or "Channel"),
                added=target.id,
            ),
            parse_mode=ParseMode.HTML,
        )
    except (RPCError, PyMongoError, RedisError, OSError) as exc:
        LOGGER.exception("Search channel configuration failed for chat %s", cid)
        await message.reply(telegram_error_text(exc) or tr("requests.could_not_add_channel"))


@command(
    ["rmchannel", "delchannel", "removechannel"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group",
)
@anonadmin_checker
async def rm_channel_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await reply_usage(message)
        return
    removed = await rdb.remove_channel(cid, message.command[1])
    await message.reply(
        tr("requests.removed_channel") if removed else tr("requests.channel_not_found_search_pool")
    )


@command(
    ["channels", "reqchannels", "reqsettings"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group",
)
@anonadmin_checker
async def channels_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    s = await rdb.get_settings(cid)
    req_t = s.get("req_title") or s.get("req_channel") or tr("requests.not_configured")
    daily_lim = s.get("daily_limit", 0)
    lim_str = f"{daily_lim}/day" if daily_lim > 0 else "Unlimited"

    lines = [
        tr(
            "requests.request_settings_request_channel_status_daily_limit_search",
            g_bullet=G_BULLET,
            req_t=req_t,
            g_bullet_2=G_BULLET,
            status="Enabled" if s.get("is_enabled", True) else "Disabled",
            g_bullet_3=G_BULLET,
            lim_str=lim_str,
        )
    ]
    for idx, c in enumerate(s.get("channels", []), 1):
        lines.append(f"{G_BULLET} **{idx}. {c.get('title')}** — `{c.get('id')}`")
    if not s.get("channels"):
        lines.append(tr("requests.none_use_addchannel"))
    await message.reply("\n".join(lines))


@command(
    ["reqmode", "requestmode"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group",
)
@anonadmin_checker
async def req_mode_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await reply_usage(message)
        return
    enable = message.command[1].lower() in ("on", "enable", "yes", "true")
    await rdb.update_settings(cid, {"is_enabled": enable})
    await message.reply(
        tr(
            "requests.content_requests_now",
            content_requests_now="enabled" if enable else "disabled",
        )
    )


@command(
    ["reqlimit", "requestlimit"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group",
)
@anonadmin_checker
async def req_limit_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        curr = await rdb.get_req_limit(cid)
        curr_str = (
            tr("requests.requests_day", limit=curr)
            if curr > 0
            else tr("requests.disabled_unlimited")
        )
        await message.reply(
            tr("requests.daily_request_limit_current_limit_usage_reqlimit_set", curr_str=curr_str)
        )
        return
    arg = message.command[1].strip().lower()
    limit = 0 if arg in ("0", "off", "disable", "none") else int(arg) if arg.isdigit() else None
    if limit is None or limit < 0:
        await reply_usage(message)
        return
    await rdb.set_req_limit(cid, limit)
    limit_str = (
        tr("requests.requests_day", limit=limit) if limit > 0 else tr("requests.disabled_unlimited")
    )
    await message.reply(tr("requests.daily_request_limit_has_been_set_to", limit_str=limit_str))


@command(
    ["reqdone", "fulfillreq", "requestdone"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group_or_channel",
)
@anonadmin_checker
async def req_done_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await reply_usage(message)
        return

    raw_id = message.command[1]
    doc = await rdb.get_request(raw_id)
    if not doc:
        await message.reply(tr("requests.no_request_found_id", raw_id=raw_id))
        return
    if cid not in {doc.get("chat_id"), doc.get("req_channel")}:
        return await message.reply(tr("permissions.request_admin_required"))

    post_url = None
    if len(message.command) > 2:
        post_url = message.command[2].strip()
    else:
        reply = message.reply_to_message
        if reply and (reply.document or reply.video or reply.audio or reply.photo):
            post_url = reply.link
        elif message.chat.username:
            post_url = f"https://t.me/{message.chat.username}"

    upd = await rdb.update_request_status(doc["num"], "completed", post_url=post_url)
    if upd:
        _broadcast_update(client, upd)
        subs = len(upd.get("subscribers", []))
        clean_q = _clean_markdown(upd.get("query", ""))
        link_str = tr("requests.post_open_link", post_url=post_url) if post_url else ""
        await message.reply(
            tr(
                "requests.request_completed_req_content_notified_subscriber_s_pm",
                num=upd["num"],
                clean_q=clean_q,
                link_str=link_str,
                subs=subs,
            )
        )


@command(
    ["reqreject", "requestreject", "delreq"],
    rate_limit=Config.RATE_LIMIT_HEAVY,
    allow_connected=True,
    chat_scope="group_or_channel",
)
@anonadmin_checker
async def req_reject_cmd(client: Client, message: Message):
    cid = await _check_admin(message)
    if cid is None:
        return
    if len(message.command) < 2:
        await reply_usage(message)
        return

    raw_id = message.command[1]
    reason = (
        " ".join(message.command[2:])
        if len(message.command) > 2
        else tr("requests.unavailable_rejected_admin")
    )
    doc = await rdb.get_request(raw_id)
    if not doc:
        await message.reply(tr("requests.no_request_found_id", raw_id=raw_id))
        return
    if cid not in {doc.get("chat_id"), doc.get("req_channel")}:
        return await message.reply(tr("permissions.request_admin_required"))

    upd = await rdb.update_request_status(doc["num"], "rejected", reason=reason)
    if upd:
        _broadcast_update(client, upd)
        subs = len(upd.get("subscribers", []))
        clean_q = _clean_markdown(upd.get("query", ""))
        await message.reply(
            tr(
                "requests.request_rejected_req_content_reason_notified_subscriber_s",
                num=upd["num"],
                clean_q=clean_q,
                reason=reason,
                subs=subs,
            )
        )


@callbackquery(
    filters=filters.regex("^req:metoo:(req_\\d+|\\d+)"), access=CallbackAccess(public=True)
)
async def cb_metoo(client: Client, query: CallbackQuery):
    req_id = query.data.split(":")[2]
    doc = await rdb.get_request(req_id)
    if not doc:
        await query.answer(tr("requests.request_not_found"), show_alert=True)
        return
    if query.from_user.id in doc.get("subscribers", []):
        await query.answer(
            tr("requests.you_are_already_subscribed_to_this_request"),
            show_alert=False,
        )
        return
    await rdb.add_subscriber(doc["num"], query.from_user.id)
    upd = await rdb.get_request(doc["num"]) or doc
    await query.answer(tr("requests.subscribed_req_alerts", num=doc["num"]), show_alert=True)
    try:
        _, markup = _render_req_card(upd, client=client)
        await query.message.edit_reply_markup(reply_markup=markup)
    except (RPCError, OSError):
        pass


@callbackquery(
    filters=filters.regex("^req:(done|reject):(req_\\d+|\\d+)"), access=CallbackAccess(public=True)
)
async def cb_admin_action(client: Client, query: CallbackQuery):
    act, req_id = query.data.split(":")[1], query.data.split(":")[2]
    doc = await rdb.get_request(req_id)
    if not doc or doc.get("status") != "pending":
        await query.answer(
            tr(
                "requests.request_already",
                status=doc.get("status") if doc else "not found",
            ),
            show_alert=True,
        )
        return
    if query.message.chat.id != doc.get("req_channel"):
        return await query.answer(
            tr("requests.this_action_is_only_allowed_for_channel"), show_alert=True
        )

    if not await has_chat_permission(client, query.message.chat.id, query.from_user.id):
        await permission_denied(query, "permissions.admin_required")
        return

    if act == "done":
        reply = query.message.reply_to_message
        post_url = None
        if reply and (reply.document or reply.video or reply.audio or reply.photo or reply.text):
            post_url = reply.link
        elif query.message.chat.username:
            post_url = f"https://t.me/{query.message.chat.username}"

        upd = await rdb.update_request_status(doc["num"], "completed", post_url=post_url)
        await query.answer(
            tr("requests.marked_completed_notifying_subscribers_in_pm"),
            show_alert=False,
        )
    else:
        upd = await rdb.update_request_status(
            doc["num"], "rejected", reason=tr("requests.rejected_admin")
        )
        await query.answer(tr("requests.request_rejected"), show_alert=False)

    if upd:
        text, _ = _render_req_card(upd, is_admin=True, client=client)
        try:
            await query.message.edit_text(
                text, link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except (RPCError, OSError):
            pass
        _broadcast_update(client, upd)
