import json
import math
import sys
import tempfile
from pathlib import Path

from pyrogram.enums import ParseMode

from Emilia.utils.archive import download_bounded
from Emilia.utils.executors import run_in_thread
from Emilia.utils.message_content import formatted_text
from Emilia.utils.process import run_process
from Emilia.utils.saved_message import SavedMessageType
from Emilia.utils.tasks import finish_cleanup

# Keep rendering in a killable subprocess and retain the sticker's frame timing.
_RENDER_TGS = """
import math
import sys
from pathlib import Path
from lottie.exporters.cairo import PngRenderer
from lottie.parsers.tgs import parse_tgs

animation = parse_tgs(sys.argv[1])
start, end = math.ceil(animation.in_point), math.ceil(animation.out_point)
fps = animation.frame_rate
if not (0 < fps <= 60 and 0 < end - start <= 180
        and 0 < animation.width <= 512 and 0 < animation.height <= 512):
    raise ValueError("Invalid Telegram sticker dimensions or timing")
with PngRenderer(animation, 96) as renderer:
    for index, frame in enumerate(range(start, end)):
        renderer.serialize(frame, str(Path(sys.argv[2]) / f"frame-{index:03d}.png"))
print(fps)
"""


async def _upload_video(message, path, options):
    result = await run_process(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        str(path),
    )
    if result.returncode:
        raise ValueError("Could not read the welcome video")
    try:
        metadata = json.loads(result.stdout)
        stream = metadata["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        duration = float(metadata["format"]["duration"])
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise ValueError("Invalid welcome video metadata") from error
    if width <= 0 or height <= 0 or not math.isfinite(duration) or duration <= 0:
        raise ValueError("Invalid welcome video dimensions or duration")
    sent = await message.reply_video(
        str(path),
        supports_streaming=True,
        width=width,
        height=height,
        duration=math.ceil(duration),
        **options,
    )
    return sent.video.file_id, SavedMessageType.video.value


async def convert_welcome_media(client, message, text, data_type):
    """Upload captionable media and return a reusable Telegram file ID."""
    source = message.reply_to_message or message
    document = formatted_text(text)
    options = {
        "caption": document.text,
        "caption_entities": document.entities,
        "parse_mode": ParseMode.DISABLED,
    }
    with tempfile.TemporaryDirectory(prefix="emilia-welcome-") as directory:
        downloaded = await download_bounded(client, source, directory)
        if data_type == SavedMessageType.video_note.value:
            # Video notes already contain MP4 video; re-upload it as a regular video.
            video = Path(directory) / "welcome.mp4"
            Path(downloaded).rename(video)
            return await _upload_video(message, video, options)

        sticker = source.sticker
        input_options = []
        if sticker.is_animated:
            result = await run_process(
                sys.executable,
                "-c",
                _RENDER_TGS,
                downloaded,
                directory,
                timeout=90,
            )
            if result.returncode:
                raise ValueError("Could not render the animated sticker")
            input_options = ["-framerate", result.stdout.strip()]
            downloaded = str(Path(directory) / "frame-%03d.png")

        if sticker.is_animated or sticker.is_video:
            video = str(Path(directory) / "welcome.mp4")
            result = await run_process(
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                *input_options,
                "-i",
                downloaded,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "pad=ceil(iw/2)*2:ceil(ih/2)*2",
                "-movflags",
                "+faststart",
                video,
            )
            if result.returncode or not Path(video).is_file():
                raise ValueError("Could not convert the sticker to video")
            return await _upload_video(message, video, options)
        else:
            from Emilia.modules.stickers import resize_image_sync

            image = await finish_cleanup(run_in_thread(resize_image_sync, downloaded))
        sent = await message.reply_photo(image, **options)
        return sent.photo.file_id, SavedMessageType.photo.value
