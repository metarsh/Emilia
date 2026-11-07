import html
import logging
import traceback

from pyrogram import errors
from pyrogram.enums import ParseMode

from Emilia.config import Config
from Emilia.locales import tr
from Emilia.utils.logging import redact

LOGGER = logging.getLogger("Emilia")

_TELEGRAM_ERRORS = {
    errors.ChatSendPlainForbidden: "permissions.bot_send_text_required",
    errors.ChatAdminRequired: "permissions.bot_admin_required",
    errors.AdminsTooMuch: "errors.admin_limit_reached",
    errors.AdminRankInvalid: "errors.invalid_admin_title",
    errors.BotChannelsNa: "errors.admin_promoted_by_another",
    errors.AdminRankEmojiNotAllowed: "errors.admin_title_emoji",
    errors.PhotoCropSizeSmall: "errors.image_too_small",
    errors.ImageProcessFailed: "errors.image_processing_failed",
    errors.ChatAboutNotModified: "errors.about_unchanged",
    errors.ChatAboutTooLong: "errors.about_too_long",
    errors.ChatSendMediaForbidden: "permissions.bot_send_media_required",
    errors.ChatSendGifsForbidden: "permissions.bot_send_gifs_required",
    errors.ChatSendStickersForbidden: "permissions.bot_send_stickers_required",
    errors.ChatNotModified: "errors.chat_title_unchanged",
    errors.TopicDeleted: "errors.topic_deleted",
    errors.ChannelInvalid: "errors.chat_unavailable",
}


def telegram_error_text(error: BaseException) -> str | None:
    if isinstance(error, errors.FloodWait):
        return tr("errors.telegram_rate_limited", seconds=error.value)
    key = _TELEGRAM_ERRORS.get(type(error))
    return tr(key) if key else None


async def report_error(scope: str, exc: BaseException, **context) -> None:
    detail = " ".join(f"{key}={value}" for key, value in context.items())[:500]
    LOGGER.error("[%s] %s: %s %s", scope, type(exc).__name__, exc, detail, exc_info=exc)
    await forward_traceback(
        scope, "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)), detail
    )


async def forward_traceback(scope: str, tb: str, detail: str = "") -> None:
    if not Config.EVENT_LOGS:
        return
    header = f"#ERROR #{redact(scope).upper().replace('.', '_')[:100]}"
    if detail:
        header += f"\n{redact(detail)[:500]}"
    body = html.escape(redact(tb)[-3500:])[-3000:]
    try:
        from Emilia.application import pgram

        await pgram.send_message(
            Config.EVENT_LOGS,
            tr("errors.traceback", header=html.escape(header), traceback=body),
            parse_mode=ParseMode.HTML,
        )
    except (errors.RPCError, TimeoutError, OSError) as error:
        LOGGER.warning("[%s] could not reach the log channel: %s", scope, error)
