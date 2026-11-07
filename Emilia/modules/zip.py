import tempfile
import zipfile
from pathlib import Path

from pyrogram.enums import ChatType, ParseMode
from pyrogram.types import ReplyParameters

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.archive import (
    InvalidFileError,
    create_zip,
    download_bounded,
    extract_zip,
    run_archive,
)
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.forward_origin import fwd_date


async def _archive_command(client, message, *, extract=False):
    if fwd_date(message):
        return
    if not message.reply_to_message:
        return await message.reply_text(
            tr("zip.reply_zip_file") if extract else tr("zip.reply_file")
        )
    if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
        sender_id = message.from_user.id if message.from_user else None
        if not await is_user_admin(message, user_id=sender_id, silent=False):
            return
    status = await message.reply_text(tr("zip.processing"))
    directory = Path(Config.TEMP_DOWNLOAD_DIRECTORY)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="archive-", dir=directory) as temporary:
            source = await download_bounded(client, message.reply_to_message, temporary)
            if extract:
                paths = await run_archive(extract_zip, source, Path(temporary) / "extracted")
            else:
                paths = [await run_archive(create_zip, source, source + ".zip")]
            for path in paths:
                await client.send_document(
                    message.chat.id,
                    path,
                    reply_parameters=ReplyParameters(message_id=message.id),
                )
        await status.edit_text(tr("zip.done"))
    except InvalidFileError as error:
        await status.edit_text(str(error), parse_mode=ParseMode.DISABLED)
    except zipfile.BadZipFile:
        LOGGER.warning("Invalid ZIP archive in chat %s", message.chat.id, exc_info=True)
        await status.edit_text(tr("zip.invalid_archive"))
    except NotImplementedError:
        await status.edit_text(tr("zip.unsupported_archive"))
    except (ValueError, OSError):
        LOGGER.exception("Archive processing failed in chat %s", message.chat.id)
        await status.edit_text(tr("zip.processing_failed"))


@command("zip", rate_limit=Config.RATE_LIMIT_HEAVY)
async def zip_command(client, message):
    return await _archive_command(client, message)


@command("unzip", rate_limit=Config.RATE_LIMIT_HEAVY)
async def unzip_command(client, message):
    return await _archive_command(client, message, extract=True)
