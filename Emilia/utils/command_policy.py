from pyrogram.enums import ChatType
from pyrogram.types import CallbackQuery, InlineQuery, Message

from Emilia.locales import tr
from Emilia.services.rate_limit import check_limit, claim_notice
from Emilia.utils.chat_context import effective_chat
from Emilia.utils.client_context import bot_id
from Emilia.utils.message_actor import actor_id

CHAT_SCOPES = {
    "any": (ChatType.PRIVATE, ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL),
    "group": (ChatType.GROUP, ChatType.SUPERGROUP),
    "supergroup": (ChatType.SUPERGROUP,),
    "supergroup_or_channel": (ChatType.SUPERGROUP, ChatType.CHANNEL),
    "private": (ChatType.PRIVATE,),
    "group_or_channel": (ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL),
}


async def check_chat_scope(message, scope="any", *, allow_connected=False):
    event = message
    message = getattr(event, "message", None) or event
    denial_key = (
        "errors.private_only"
        if scope == "private"
        else "errors.supergroup_only"
        if scope == "supergroup"
        else "errors.supergroup_or_channel_only"
        if scope == "supergroup_or_channel"
        else "errors.group_only"
    )
    if allow_connected and message.chat.type == ChatType.PRIVATE:
        from Emilia.utils.connections import connection

        target = await connection(message)
        if target is not None:
            if effective_chat(message).type in CHAT_SCOPES[scope]:
                return True
            await answer_denial(event, tr(denial_key), alert=True)
            return False
    if message.chat.type in CHAT_SCOPES[scope]:
        return True
    text = tr(denial_key)
    await answer_denial(event, text, alert=True)
    return False


async def enforce_rate_limit(client, update, name, limit):
    if limit is None:
        return True
    message = getattr(update, "message", None) or update
    chat = getattr(message, "chat", None)
    identity = actor_id(update) or getattr(chat, "id", 0)
    key = f"{bot_id(client)}:{identity}:{name}"
    result = await check_limit(key, *limit)
    if result.allowed:
        return True
    notify = await claim_notice(key)
    if notify:
        text = tr(
            "decorators.please_try_again_seconds",
            please_try_again=max(1, round(result.retry_after)),
        )
        await answer_denial(update, text)
    elif isinstance(update, (CallbackQuery, InlineQuery)):
        await answer_denial(update)
    return False


async def answer_denial(update, text=None, *, alert=False):
    if isinstance(update, CallbackQuery):
        await update.answer(text, show_alert=alert)
    elif isinstance(update, InlineQuery):
        await update.answer([], cache_time=0, is_personal=True)
    elif isinstance(update, Message) and text:
        await update.reply_text(text)
