import asyncio
import os
import tempfile
import threading
from contextlib import suppress
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from pyrogram import Client, enums
from pyrogram.errors import RPCError

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.archive import download_bounded
from Emilia.utils.command_help import reply_usage
from Emilia.utils.process import run_process
from Emilia.utils.tasks import finish_cleanup

MODEL_REPO = "BritishWerewolf/U-2-Netp"
MODEL_FILE = "onnx/model.onnx"
MODEL_SIZE = 320

IMAGE_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
VIDEO_EXTENSIONS = {".m4v", ".mkv", ".mov", ".mp4", ".webm"}

_model_session = None
_model_input_name = None
_model_lock = threading.Lock()
_inference_slots = asyncio.Semaphore(2)


class InvalidMediaError(ValueError):
    """Unsupported or unreadable media supplied by the user."""


def _document_extension(document) -> str:
    return Path(getattr(document, "file_name", "") or "").suffix.lower()


def _is_image_document(document) -> bool:
    mime_type = (getattr(document, "mime_type", "") or "").lower()
    return mime_type.startswith("image/") or _document_extension(document) in IMAGE_EXTENSIONS


def _is_video_document(document) -> bool:
    mime_type = (getattr(document, "mime_type", "") or "").lower()
    return mime_type.startswith("video/") or _document_extension(document) in VIDEO_EXTENSIONS


def _load_model():
    global _model_session, _model_input_name

    with _model_lock:
        if _model_session is not None:
            return _model_session, _model_input_name

        import onnxruntime as ort
        from huggingface_hub import hf_hub_download

        try:
            model_path = hf_hub_download(repo_id=MODEL_REPO, filename=MODEL_FILE)
            session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            input_name = session.get_inputs()[0].name
        except Exception as exc:
            raise RuntimeError("Could not initialize the background-removal model") from exc

        _model_session, _model_input_name = session, input_name
        return session, input_name


def _image_to_tensor(image: Image.Image):
    width, height = image.size
    scale = min(MODEL_SIZE / width, MODEL_SIZE / height)
    resized_size = (max(1, round(width * scale)), max(1, round(height * scale)))

    rgba = image.convert("RGBA")
    rgb = Image.new("RGB", rgba.size, (255, 255, 255))
    rgb.paste(rgba.convert("RGB"), mask=rgba.getchannel("A"))

    resized = rgb.resize(resized_size, Image.Resampling.LANCZOS)
    padded = Image.new("RGB", (MODEL_SIZE, MODEL_SIZE), (0, 0, 0))
    left = (MODEL_SIZE - resized_size[0]) // 2
    top = (MODEL_SIZE - resized_size[1]) // 2
    padded.paste(resized, (left, top))

    tensor = np.asarray(padded).astype(np.float32) / 255.0
    tensor = (tensor - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]
    tensor = np.transpose(tensor, (2, 0, 1))[None, ...].astype(np.float32)

    crop_box = (left, top, left + resized_size[0], top + resized_size[1])
    return tensor, crop_box


def _output_to_mask(output, crop_box, original_size) -> Image.Image:
    mask = np.squeeze(output).astype(np.float32)
    if mask.ndim > 2:
        mask = mask[0]

    min_value = float(mask.min())
    max_value = float(mask.max())
    if max_value > min_value:
        mask = (mask - min_value) / (max_value - min_value)

    mask = np.clip(mask * 255, 0, 255).astype(np.uint8)
    mask = Image.fromarray(mask, mode="L").crop(crop_box)
    return mask.resize(original_size, Image.Resampling.LANCZOS)


def _remove_background_sync(input_path: str, output_path: str) -> str:
    try:
        with Image.open(input_path) as image:
            image.load()
            original = ImageOps.exif_transpose(image).convert("RGBA")
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidMediaError(
            "I could not read that file as an image. Send a photo, image document, or static sticker."
        ) from exc

    session, input_name = _load_model()
    tensor, crop_box = _image_to_tensor(original)
    mask = _output_to_mask(session.run(None, {input_name: tensor})[0], crop_box, original.size)

    old_alpha = np.asarray(original.getchannel("A")).astype(np.float32) / 255.0
    new_alpha = np.asarray(mask).astype(np.float32) / 255.0
    alpha = np.clip(old_alpha * new_alpha * 255, 0, 255).astype(np.uint8)

    result = original.copy()
    result.putalpha(Image.fromarray(alpha, mode="L"))
    result.save(output_path, format="PNG")
    return output_path


async def _remove_background(input_path: str, output_path: str) -> str:
    async with _inference_slots:
        return await finish_cleanup(
            asyncio.to_thread(_remove_background_sync, input_path, output_path)
        )


async def _extract_first_frame(video_path: str, tempdir: str) -> str:
    frame_path = os.path.join(tempdir, "frame.png")
    try:
        result = await run_process(
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            video_path,
            "-frames:v",
            "1",
            frame_path,
            timeout=30,
        )
    except FileNotFoundError as exc:
        raise InvalidMediaError(
            "Video stickers need ffmpeg installed before I can read them."
        ) from exc
    if result.returncode:
        LOGGER.warning("Sticker frame extraction failed: %s", result.stderr)
        raise InvalidMediaError(tr("rmbg.could_not_extract_image_frame_from_video_sticker"))
    return frame_path


async def _message_to_image_path(client: Client, message, tempdir: str) -> str:
    if message.photo:
        return await download_bounded(client, message, tempdir)

    if message.sticker:
        if message.sticker.is_animated:
            raise InvalidMediaError(
                "Animated .tgs stickers are not raster images. Send a static sticker, video sticker, or image."
            )
        downloaded = await download_bounded(client, message, tempdir)
        if message.sticker.is_video:
            return await _extract_first_frame(downloaded, tempdir)
        return downloaded

    if message.document:
        if _is_image_document(message.document):
            return await download_bounded(client, message, tempdir)
        if _is_video_document(message.document):
            downloaded = await download_bounded(client, message, tempdir)
            return await _extract_first_frame(downloaded, tempdir)

    if message.animation or message.video:
        downloaded = await download_bounded(client, message, tempdir)
        return await _extract_first_frame(downloaded, tempdir)

    raise InvalidMediaError(
        "Reply to a photo, image document, static sticker, or video sticker so I can remove its background."
    )


@command("rmbg", disable=True, rate_limit=Config.RATE_LIMIT_HEAVY)
async def remove_bg_command_handler(client, message):
    if not message.reply_to_message:
        return await reply_usage(message)

    status = await message.reply_text(tr("rmbg.removing_background"))

    try:
        await client.send_chat_action(message.chat.id, enums.ChatAction.UPLOAD_PHOTO)
        with tempfile.TemporaryDirectory(prefix="emilia_rmbg_") as tempdir:
            input_path = await _message_to_image_path(client, message.reply_to_message, tempdir)
            output_path = os.path.join(tempdir, "rmbg.png")
            await _remove_background(input_path, output_path)

            await message.reply_photo(photo=output_path)
            await message.reply_document(document=output_path, file_name="rmbg.png")
    except InvalidMediaError as exc:
        await status.edit_text(str(exc))
    except Exception:
        LOGGER.exception("Unexpected error while removing background")
        await status.edit_text(tr("rmbg.i_could_not_remove_the_background_from"))
    else:
        with suppress(RPCError):
            await status.delete()
