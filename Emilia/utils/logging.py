import asyncio
import logging
import re
from logging.handlers import QueueHandler, QueueListener

from pyrogram.errors import RPCError

from Emilia.config import Config
from Emilia.utils.trace import TRACE_ID

_TOKEN = re.compile(r"(?:bot)?\d{5,15}:[A-Za-z0-9_-]{20,}")
_URI = re.compile(r"((?:mongodb(?:\+srv)?|rediss?|postgres(?:ql)?)://)[^\s\"']+")
_PARAM = re.compile(r"(?i)((?:api[_-]?key|token|password|secret|authorization)=)[^&\s\"']+")
_VALUES = tuple(
    str(getattr(Config, name))
    for name in (
        "TOKEN",
        "API_HASH",
        "GROQ_API_KEY",
        "CARTESIA_API_KEY",
        "ANILIST_SECRET",
        "SESSION_STRING",
        "SAUCENAO_API_KEY",
        "GIPHY_API_KEY",
        "REDIS_PASSWORD",
        "ZIPLINE_TOKEN",
        "ZIPLINE_PASSWORD",
    )
    if getattr(Config, name, None) and len(str(getattr(Config, name))) >= 8
)


def redact(message: str) -> str:
    message = _TOKEN.sub("[redacted token]", str(message))
    message = _URI.sub(r"\1[redacted]", message)
    message = _PARAM.sub(r"\1[redacted]", message)
    for secret in _VALUES:
        message = message.replace(secret, "[redacted]")
    return message


class RedactingQueueHandler(QueueHandler):
    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        prepared = super().prepare(record)
        prepared.msg = redact(prepared.getMessage())
        if TRACE_ID.get():
            prepared.emilia = {**getattr(prepared, "emilia", {}), "trace": TRACE_ID.get()}
        return prepared


class DrainingQueueListener(QueueListener):
    def enqueue_sentinel(self):
        self.queue.put(self._sentinel)


async def stop_listener(listener):
    """Detach producers, drain queued records and close every output handler."""
    root = logging.getLogger()
    errors = []
    for handler in tuple(root.handlers):
        if getattr(handler, "queue", None) is listener.queue:
            root.removeHandler(handler)
            try:
                handler.close()
            except Exception as exc:
                errors.append(exc)
    try:
        await asyncio.to_thread(listener.stop)
    except Exception as exc:
        errors.append(exc)
    for handler in listener.handlers:
        try:
            handler.flush()
        except Exception as exc:
            errors.append(exc)
        try:
            handler.close()
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup("Log handlers failed during shutdown", errors)


async def log_bot_join(client, update):
    from pyrogram.enums import ParseMode

    from Emilia.application import LOGGER, pgram
    from Emilia.locales import tr
    from Emilia.utils.client_context import bot_id, bot_username

    user_id = getattr(getattr(update, "from_user", None), "id", None)
    payload = {
        "event": "bot_joined",
        "bot_id": bot_id(client),
        "chat_id": update.chat.id,
        "user_id": user_id,
    }
    LOGGER.info("bot_joined", extra={"emilia": payload})
    if not Config.EVENT_LOGS:
        return
    try:
        await pgram.send_message(
            Config.EVENT_LOGS,
            tr(
                "logging.bot_joined",
                bot_username=bot_username(client),
                bot_id=payload["bot_id"],
                chat_title=update.chat.title or str(update.chat.id),
                chat_id=update.chat.id,
                user_id=user_id or "unknown",
            ),
            parse_mode=ParseMode.DISABLED,
        )
    except (RPCError, OSError) as error:
        LOGGER.warning(
            "bot_join_report_failed",
            extra={"emilia": {**payload, "event": "bot_join_report_failed", "error": str(error)}},
        )
