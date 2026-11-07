import asyncio
import os
import textwrap
from contextlib import suppress
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pyrogram.errors import RPCError

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.command_help import reply_usage
from Emilia.utils.forward_origin import fwd_date
from Emilia.utils.tasks import finish_cleanup

IMAGE_EXTENSIONS = (".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp")


def _get_target_media(reply_message):
    if not reply_message:
        return None

    if getattr(reply_message, "photo", None):
        return reply_message.photo

    if getattr(reply_message, "sticker", None):
        if getattr(reply_message.sticker, "is_animated", False):
            return None
        if getattr(reply_message.sticker, "is_video", False):
            if getattr(reply_message.sticker, "thumbs", None):
                return reply_message.sticker.thumbs[-1]
            return None
        return reply_message.sticker

    if getattr(reply_message, "document", None):
        mime = (getattr(reply_message.document, "mime_type", "") or "").lower()
        file_name = (getattr(reply_message.document, "file_name", "") or "").lower()
        if mime.startswith("image/") or any(file_name.endswith(ext) for ext in IMAGE_EXTENSIONS):
            return reply_message.document
        if getattr(reply_message.document, "thumbs", None):
            return reply_message.document.thumbs[-1]
        return None

    if getattr(reply_message, "animation", None):
        if getattr(reply_message.animation, "thumbs", None):
            return reply_message.animation.thumbs[-1]
        return None

    if getattr(reply_message, "video", None):
        if getattr(reply_message.video, "thumbs", None):
            return reply_message.video.thumbs[-1]
        return None

    if getattr(reply_message, "video_note", None):
        if getattr(reply_message.video_note, "thumbs", None):
            return reply_message.video_note.thumbs[-1]
        return None

    if getattr(reply_message, "audio", None):
        if getattr(reply_message.audio, "thumbs", None):
            return reply_message.audio.thumbs[-1]
        return None

    return None


@command("mmf", disable=True)
async def handler(client, message):
    if fwd_date(message):
        return
    if not message.reply_to_message_id:
        return await reply_usage(message, handler)
    reply_message = message.reply_to_message
    if not reply_message:
        return await reply_usage(message)

    target_media = _get_target_media(reply_message)
    if not target_media:
        return await reply_usage(message)

    parts = (message.text or "").split(None, 1)
    text = parts[1] if len(parts) > 1 else ""
    if len(text) < 1:
        return await message.reply_text(tr("memify.you_might_want_to_try_mmf_text"))

    msg = await message.reply_text(tr("memify.memifying_this_image"))
    file = None
    try:
        file = await client.download_media(target_media, in_memory=False)
        if not file or not os.path.exists(file):
            await msg.edit_text(tr("memify.failed_to_download_media"))
            return

        rendered = await finish_cleanup(asyncio.to_thread(drawText, file, text))
        with BytesIO(rendered) as meme:
            meme.name = "meme.webp"
            await client.send_sticker(message.chat.id, meme)
    except (RPCError, OSError, ValueError, Image.DecompressionBombError):
        LOGGER.exception("Meme rendering or delivery failed")
        await msg.edit_text(tr("memify.processing_failed"))
    else:
        with suppress(RPCError):
            await msg.delete()
    finally:
        if file:
            with suppress(OSError):
                os.remove(file)


def drawText(image_path, text):
    with Image.open(image_path) as img:
        i_width, i_height = img.size
        fnt = str(Path(Config.FONT_DIRECTORY) / "DejaVuSans-Bold.ttf")
        m_font = ImageFont.truetype(fnt, int((70 / 640) * i_width))

        if ";" in text:
            upper_text, lower_text = text.split(";", 1)
        else:
            upper_text = text
            lower_text = ""
        draw = ImageDraw.Draw(img)
        current_h, pad = 10, 5
        if upper_text:
            for u_text in textwrap.wrap(upper_text, width=15):
                u_bbox = draw.textbbox((0, 0), u_text, font=m_font)
                u_width, u_height = (u_bbox[2] - u_bbox[0], u_bbox[3] - u_bbox[1])
                draw.text(
                    xy=(((i_width - u_width) / 2) - 2, int((current_h / 640) * i_width)),
                    text=u_text,
                    font=m_font,
                    fill=(0, 0, 0),
                )
                draw.text(
                    xy=(((i_width - u_width) / 2) + 2, int((current_h / 640) * i_width)),
                    text=u_text,
                    font=m_font,
                    fill=(0, 0, 0),
                )
                draw.text(
                    xy=((i_width - u_width) / 2, int((current_h / 640) * i_width) - 2),
                    text=u_text,
                    font=m_font,
                    fill=(0, 0, 0),
                )
                draw.text(
                    xy=(((i_width - u_width) / 2), int((current_h / 640) * i_width) + 2),
                    text=u_text,
                    font=m_font,
                    fill=(0, 0, 0),
                )

                draw.text(
                    xy=((i_width - u_width) / 2, int((current_h / 640) * i_width)),
                    text=u_text,
                    font=m_font,
                    fill=(255, 255, 255),
                )
                current_h += u_height + pad
        if lower_text:
            for l_text in textwrap.wrap(lower_text, width=15):
                l_bbox = draw.textbbox((0, 0), l_text, font=m_font)
                u_width, u_height = (l_bbox[2] - l_bbox[0], l_bbox[3] - l_bbox[1])
                draw.text(
                    xy=(
                        ((i_width - u_width) / 2) - 2,
                        i_height - u_height - int((20 / 640) * i_width),
                    ),
                    text=l_text,
                    font=m_font,
                    fill=(0, 0, 0),
                )
                draw.text(
                    xy=(
                        ((i_width - u_width) / 2) + 2,
                        i_height - u_height - int((20 / 640) * i_width),
                    ),
                    text=l_text,
                    font=m_font,
                    fill=(0, 0, 0),
                )
                draw.text(
                    xy=(
                        (i_width - u_width) / 2,
                        (i_height - u_height - int((20 / 640) * i_width)) - 2,
                    ),
                    text=l_text,
                    font=m_font,
                    fill=(0, 0, 0),
                )
                draw.text(
                    xy=(
                        (i_width - u_width) / 2,
                        (i_height - u_height - int((20 / 640) * i_width)) + 2,
                    ),
                    text=l_text,
                    font=m_font,
                    fill=(0, 0, 0),
                )

                draw.text(
                    xy=(
                        (i_width - u_width) / 2,
                        i_height - u_height - int((20 / 640) * i_width),
                    ),
                    text=l_text,
                    font=m_font,
                    fill=(255, 255, 255),
                )
                current_h += u_height + pad

        with BytesIO() as output:
            img.save(output, "webp")
            return output.getvalue()
