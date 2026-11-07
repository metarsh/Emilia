import os
import tempfile
import time
from pathlib import Path

from aiohttp import ClientError
from PIL import Image
from pyrogram.types import LinkPreviewOptions

from Emilia.application import LOGGER
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.archive import download_bounded
from Emilia.utils.command_help import reply_usage
from Emilia.utils.executors import run_in_thread
from Emilia.utils.forward_origin import fwd_date
from Emilia.utils.tasks import finish_cleanup
from Emilia.utils.uploader import TMP_DOWNLOAD_DIRECTORY, upload_local_file


@command(pattern="t(gm|gt)")
async def _(client, message):
    if fwd_date(message):
        return
    if message.reply_to_message_id:
        r_message = message.reply_to_message
        if r_message is None:
            await message.reply_text(tr("telegraph.can_t_access_the_replied_message_it"))
            return

        text_content = r_message.text or r_message.caption
        start = time.monotonic()

        os.makedirs(TMP_DOWNLOAD_DIRECTORY, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=TMP_DOWNLOAD_DIRECTORY) as directory:
            if not r_message.media:
                if not text_content:
                    await reply_usage(message)
                    return
                downloaded_file_name = os.path.join(directory, "text.txt")
                await finish_cleanup(
                    run_in_thread(
                        Path(downloaded_file_name).write_text, text_content, encoding="utf-8"
                    )
                )
            else:
                try:
                    downloaded_file_name = await download_bounded(client, r_message, directory)
                except ValueError:
                    await reply_usage(message)
                    return

            download_seconds = int(time.monotonic() - start)
            h = await message.reply_text(
                tr(
                    "telegraph.downloaded_seconds",
                    downloaded_file_name=Path(downloaded_file_name).name,
                    downloaded=download_seconds,
                )
            )
            try:
                start = time.monotonic()
                media_urls = await upload_local_file(downloaded_file_name)
            except (ClientError, OSError, ValueError, RuntimeError, Image.DecompressionBombError):
                LOGGER.exception(f"tgm: upload_local_file failed for {downloaded_file_name}")
                await h.edit_text(tr("telegraph.upload_unavailable"))
            else:
                upload_seconds = int(time.monotonic() - start)
                await h.edit_text(
                    tr(
                        "telegraph.uploaded_zipline_seconds",
                        media_urls=media_urls,
                        ms_two=download_seconds + upload_seconds,
                    ),
                    link_preview_options=LinkPreviewOptions(is_disabled=False),
                )

    else:
        await reply_usage(message)
