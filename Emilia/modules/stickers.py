import os
import random
import re
import tempfile
from contextlib import suppress

import emoji
from aiohttp import ClientError
from PIL import Image
from pymongo import ReturnDocument
from pyrogram import enums
from pyrogram.enums import ParseMode
from pyrogram.errors import (
    BadRequest,
    PackShortNameOccupied,
    PeerIdInvalid,
    RPCError,
    StickerpackStickersTooMuch,
    StickersetInvalid,
    StickersTooMuch,
)
from pyrogram.file_id import FileId
from pyrogram.raw import functions as raw_functions
from pyrogram.raw import types as raw_types
from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.raw.functions.stickers import (
    AddStickerToSet,
    CreateStickerSet,
    RemoveStickerFromSet,
)
from pyrogram.raw.types import (
    InputDocument,
    InputStickerSetItem,
    InputStickerSetShortName,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.custom_filter import command
from Emilia.database.common import atomic_find_one_and_update
from Emilia.locales import tr
from Emilia.utils.client_context import bot_username
from Emilia.utils.command_help import reply_usage
from Emilia.utils.errors import telegram_error_text
from Emilia.utils.http import get
from Emilia.utils.process import run_process

pkang = db.pkang


def get_emoji(v):
    matches = emoji.emoji_list(v)
    return matches[0]["emoji"] if matches else None


@command(pattern="pkang|packkang", disable=True)
async def pck_kang__(client, message):
    if not message.reply_to_message_id:
        return await reply_usage(message)
    r = message.reply_to_message
    if not r.sticker:
        return await reply_usage(message)
    if len(message.text.split(" ", 1)) == 2:
        pname = message.text.split(" ", 1)[1]
        emoji_ = get_emoji(pname)
        if emoji_:
            if pname.startswith(emoji_):
                emoji_ = None
            else:
                pname = pname.replace(emoji_, "")
    else:
        pname = tr("stickers.s_pkang_pack", user_name=message.from_user.first_name)
        emoji_ = None
    if not r.sticker.set_name:
        return await message.reply_text(tr("stickers.that_sticker_is_not_part_of_any"))

    _stickers = await client.invoke(
        raw_functions.messages.GetStickerSet(
            stickerset=raw_types.InputStickerSetShortName(short_name=r.sticker.set_name),
            hash=0,
        )
    )
    stk = [
        raw_types.InputStickerSetItem(
            document=raw_types.InputDocument(
                id=document.id,
                access_hash=document.access_hash,
                file_reference=document.file_reference,
            ),
            emoji=emoji_
            or next(
                (
                    attribute.alt
                    for attribute in document.attributes
                    if isinstance(attribute, raw_types.DocumentAttributeSticker)
                ),
                "🤔",
            ),
        )
        for document in _stickers.documents
    ]
    counter = await atomic_find_one_and_update(
        pkang,
        {"user_id": message.from_user.id},
        {"$inc": {"pack": 1}},
        return_document=ReturnDocument.AFTER,
        projection={"pack": 1},
    )
    pack = counter["pack"]
    pm = random.choice(
        ["af", "bq", "cj", "dp", "eu", "fw", "g", "hu", "wuw", "uw", "hk", "lm", "jr"]
    )
    peer = await client.resolve_peer(message.from_user.id)
    input_user = raw_types.InputUser(user_id=peer.user_id, access_hash=peer.access_hash)
    try:
        p = await client.invoke(
            raw_functions.stickers.CreateStickerSet(
                user_id=input_user,
                title=pname,
                short_name=f"{pm}{message.from_user.id}_{pack}_by_{bot_username(client)}",
                stickers=stk,
            )
        )
    except PackShortNameOccupied:
        pack += 1
        p = await client.invoke(
            raw_functions.stickers.CreateStickerSet(
                user_id=input_user,
                title=pname + f"Vol {pack}",
                short_name=f"{pm}{message.from_user.id}_{pack}_by_{bot_username(client)}",
                stickers=stk,
            )
        )
    except (RPCError, OSError) as exc:
        LOGGER.exception("Sticker set creation failed")
        return await message.reply_text(telegram_error_text(exc) or tr("stickers.error"))
    await message.reply_text(
        tr("stickers.sticker_set_successfully_created_and_added_to", short_name=p.set.short_name),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("stickers.view_pack"),
                        url=f"http://t.me/addstickers/{p.set.short_name}",
                    )
                ]
            ]
        ),
        parse_mode=ParseMode.HTML,
    )


@command("stickerid", disable=True)
async def _stickidd(_, me):
    replied = me.reply_to_message
    text = tr("stickers.sticker_id")

    if replied and replied.sticker:
        await me.reply_text(text.format(replied.sticker.file_id))
    else:
        await reply_usage(me, _stickidd)
        return


@command("getsticker", disable=True)
async def _stickid0(c, m):
    replied = m.reply_to_message
    if not replied or not replied.sticker:
        return await reply_usage(m, _stickid0)
    sticker = replied.sticker
    if sticker.is_animated or sticker.is_video:
        return await m.reply_text(tr("stickers.animated_sticker_is_not_supported"))
    with tempfile.TemporaryDirectory(prefix="emilia-sticker-") as tempdir:
        sticker_file = await c.download_media(
            replied, file_name=os.path.join(tempdir, "sticker.webp")
        )
        if not sticker_file:
            return
        png = await resize_image(sticker_file)
        await replied.reply_document(
            document=png,
            caption=tr("stickers.emoji_sticker_id", emoji=sticker.emoji, file_id=sticker.file_id),
        )


@command("getvidsticker", disable=True)
async def _vidstick(_, message):
    chat_id = message.chat.id
    replied = message.reply_to_message
    if replied and replied.sticker:
        if not replied.sticker.is_video:
            return await message.reply_text(tr("stickers.use_getsticker_if_sticker_is_not_a"))
        with tempfile.TemporaryDirectory(prefix="emilia-sticker-") as tempdir:
            source = await _.download_media(
                replied, file_name=os.path.join(tempdir, "sticker.webm")
            )
            if not source:
                return
            output = os.path.join(tempdir, "sticker.mp4")
            result = await run_process(
                "ffmpeg",
                "-y",
                "-i",
                source,
                "-an",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-vf",
                "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                output,
            )
            if result.returncode:
                LOGGER.error("Sticker conversion failed: %s", result.stderr)
                return await message.reply_text(tr("stickers.error"))
            await _.send_animation(chat_id, output)
    else:
        await reply_usage(message, _vidstick)
        return


@command("getvideo", disable=True)
async def _vidstick0(_, message):
    chat_id = message.chat.id
    replied = message.reply_to_message
    if replied and replied.animation:
        downloaded = await _.download_media(replied, in_memory=True)
        if downloaded:
            with downloaded:
                downloaded.name = "animation.mp4"
                await _.send_video(chat_id, video=downloaded)
    else:
        await reply_usage(message, _vidstick0)
        return


def get_emoji_regex():
    e_list = [c.encode("unicode-escape").decode("ASCII") for c in emoji.EMOJI_DATA]
    # to avoid re.error excluding char that start with '*'
    e_sort = sorted([x for x in e_list if not x.startswith("*")], reverse=True)
    pattern_ = f"({'|'.join(e_sort)})"
    return re.compile(pattern_)


EMOJI_PATTERN = get_emoji_regex()


@command(["unkang", "delsticker"], disable=True, require_reply=True)
async def unkang(c, m):
    if m.reply_to_message.sticker:
        try:
            decoded = FileId.decode(m.reply_to_message.sticker.file_id)
            sticker = InputDocument(
                id=decoded.media_id,
                access_hash=decoded.access_hash,
                file_reference=decoded.file_reference,
            )
            await c.invoke(RemoveStickerFromSet(sticker=sticker))
            await m.reply(tr("stickers.sticker_has_been_removed_from_your_pack"))
        except Exception as exc:
            LOGGER.exception("Sticker removal failed")
            await m.reply(
                telegram_error_text(exc) or tr("stickers.failed_to_remove_sticker_from_your_pack")
            )
    else:
        await reply_usage(m, unkang)
        return


@command("kang", disable=True)
async def kang_sticker(c, m):
    if m.sender_chat:
        return await m.reply_text(tr("stickers.you_are_anonymous_please_kang_in_my"))
    sticker_emoji = "🤔"
    packnum = 0
    packname_found = False
    resize = False
    animated = False
    videos = False
    convert = False
    reply = m.reply_to_message
    peer = await c.resolve_peer(m.from_user.id)
    user = raw_types.InputUser(user_id=peer.user_id, access_hash=peer.access_hash)
    if reply and reply.media:
        if reply.photo:
            resize = True
        elif reply.animation:
            videos = True
            convert = True
        elif reply.video:
            convert = True
            videos = True
        elif reply.document:
            mime_type = reply.document.mime_type or ""
            if mime_type.startswith("image/"):
                resize = True
            elif mime_type.startswith("video/"):
                videos = True
                convert = True
            elif "tgsticker" in mime_type:
                animated = True
            else:
                return await m.reply_text(tr("stickers.error"))
        elif reply.sticker:
            if not reply.sticker.file_name:
                return await m.reply(tr("stickers.the_sticker_has_no_name"))
            if reply.sticker.emoji:
                sticker_emoji = reply.sticker.emoji
            animated = reply.sticker.is_animated
            videos = reply.sticker.is_video
            if videos:
                convert = False
            elif not reply.sticker.file_name.endswith(".tgs"):
                resize = True
        else:
            return

        pack_prefix = "anim" if animated else "vid" if videos else "a"
        packname = f"{pack_prefix}_{m.from_user.id}_by_{c.me.username}"

        if len(m.command) > 1 and m.command[1].isdigit() and int(m.command[1]) > 0:
            # provide pack number to kang in desired pack
            packnum = int(m.command.pop(1))
            packname = f"{pack_prefix}{packnum}_{m.from_user.id}_by_{c.me.username}"
        if len(m.command) > 1:
            # matches all valid emojis in input
            sticker_emoji = (
                "".join(set(EMOJI_PATTERN.findall("".join(m.command[1:])))) or sticker_emoji
            )
        filename = await c.download_media(m.reply_to_message)
        if not filename:
            # Failed to download
            return
    elif m.entities and len(m.entities) > 1:
        pack_prefix = "a"
        packname = f"c{m.from_user.id}_by_{c.me.username}"
        entity = next(
            (
                item
                for item in m.entities
                if item.type in {enums.MessageEntityType.URL, enums.MessageEntityType.TEXT_LINK}
            ),
            None,
        )
        if entity is None:
            return
        img_url = (
            entity.url
            if entity.type == enums.MessageEntityType.TEXT_LINK
            else m.text.encode("utf-16-le")[
                entity.offset * 2 : (entity.offset + entity.length) * 2
            ].decode("utf-16-le")
        )
        filename = None
        try:
            response = await get(img_url)
            response.raise_for_status()
            with tempfile.NamedTemporaryFile(
                prefix="emilia-sticker-", suffix=".png", delete=False
            ) as downloaded:
                filename = downloaded.name
                downloaded.write(response.content)
        except (ClientError, OSError, ValueError) as exc:
            LOGGER.exception("Sticker image download failed")
            if filename:
                with suppress(OSError):
                    os.remove(filename)
            return await m.reply(telegram_error_text(exc) or tr("stickers.error"))
        if len(m.command) > 2:
            # m.command[1] is image_url
            if m.command[2].isdigit() and int(m.command[2]) > 0:
                packnum = int(m.command.pop(2))
                packname = f"a{packnum}_{m.from_user.id}_by_{c.me.username}"
            if len(m.command) > 2:
                sticker_emoji = (
                    "".join(set(EMOJI_PATTERN.findall("".join(m.command[2:])))) or sticker_emoji
                )
        resize = True
    else:
        await reply_usage(m, kang_sticker)
        return
    upload_chat = Config.EVENT_LOGS or m.chat.id
    upload_message_id = None
    try:
        if resize:
            filename = await resize_image(filename)
        elif convert:
            filename = await convert_video(filename)
        max_stickers = 50 if animated else 120
        while not packname_found:
            try:
                stickerset = await c.invoke(
                    GetStickerSet(
                        stickerset=InputStickerSetShortName(short_name=packname),
                        hash=0,
                    )
                )
                if stickerset.set.count >= max_stickers:
                    packnum += 1
                    packname = f"{pack_prefix}{packnum}_{m.from_user.id}_by_{c.me.username}"
                else:
                    packname_found = True
            except StickersetInvalid:
                break
        uploaded = await c.send_document(
            upload_chat,
            filename,
            caption=tr("stickers.sticker_kang_userid", user_id=m.from_user.id),
            force_document=True,
        )
        upload_message_id = uploaded.id
        if not uploaded.document:
            raise ValueError("Sticker source did not upload as a document")
        decoded = FileId.decode(uploaded.document.file_id)
        sticker_document = InputDocument(
            id=decoded.media_id,
            access_hash=decoded.access_hash,
            file_reference=decoded.file_reference,
        )
        if packname_found:
            await c.invoke(
                AddStickerToSet(
                    stickerset=InputStickerSetShortName(short_name=packname),
                    sticker=InputStickerSetItem(
                        document=sticker_document,
                        emoji=sticker_emoji,
                    ),
                )
            )
        else:
            stkr_title = f"{m.from_user.first_name}'s"
            if animated:
                stkr_title += "AnimPack"
            elif videos:
                stkr_title += "VidPack"
            if packnum != 0:
                stkr_title += f" v{packnum}"
            try:
                await c.invoke(
                    CreateStickerSet(
                        user_id=user,
                        title=stkr_title,
                        short_name=packname,
                        stickers=[
                            InputStickerSetItem(
                                document=sticker_document,
                                emoji=sticker_emoji,
                            )
                        ],
                    )
                )
            except PeerIdInvalid:
                return await m.reply(
                    tr("stickers.it_looks_like_you_ve_never_interacted"),
                    reply_markup=InlineKeyboardMarkup(
                        [
                            [
                                InlineKeyboardButton(
                                    tr("stickers.click_me"),
                                    url=f"https://t.me/{bot_username(c)}?start",
                                )
                            ]
                        ]
                    ),
                )

    except (StickerpackStickersTooMuch, StickersTooMuch):
        return await m.reply(tr("stickers.your_sticker_pack_is_full_if_your"))
    except BadRequest as exc:
        LOGGER.exception("Sticker set mutation failed")
        return await m.reply(telegram_error_text(exc) or tr("stickers.error"))
    except (OSError, ValueError, TimeoutError):
        LOGGER.exception("Sticker media could not be processed")
        return await m.reply_text(tr("stickers.error"))
    else:
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text=tr("stickers.view_your_pack"),
                        url=f"https://t.me/addstickers/{packname}",
                    )
                ]
            ]
        )
        await m.reply(
            tr("stickers.b_sticker_successfully_stolen_b_b_emoji", sticker_emoji=sticker_emoji),
            reply_markup=markup,
        )
    finally:
        try:
            if upload_message_id is not None:
                with suppress(RPCError):
                    await c.delete_messages(
                        chat_id=upload_chat, message_ids=upload_message_id, revoke=True
                    )
        finally:
            with suppress(OSError):
                os.remove(filename)


def resize_image_sync(filename: str) -> str:
    downpath, name = os.path.split(filename)
    output = os.path.join(downpath, os.path.splitext(name)[0] + ".png")
    with Image.open(filename) as image:
        width, height = image.size
        size = (
            (512, max(1, round(height * 512 / width)))
            if width >= height
            else (max(1, round(width * 512 / height)), 512)
        )
        resized = image.resize(size, Image.Resampling.LANCZOS)
        with resized:
            resized.save(output, "PNG")
    if output != filename:
        os.remove(filename)
    return output


async def resize_image(filename: str) -> str:
    from Emilia.utils.executors import run_in_process

    return await run_in_process(resize_image_sync, filename)


async def convert_video(input_file: str) -> str:
    with tempfile.NamedTemporaryFile(
        prefix="emilia-sticker-", suffix=".webm", delete=False
    ) as output:
        filename = output.name
    try:
        result = await run_process(
            "ffmpeg",
            "-y",
            "-i",
            input_file,
            "-an",
            "-t",
            "3",
            "-vf",
            "fps=30,scale=512:512:force_original_aspect_ratio=decrease",
            "-c:v",
            "libvpx-vp9",
            "-crf",
            "30",
            filename,
        )
        if result.returncode:
            raise ValueError("Sticker video conversion failed")
        os.remove(input_file)
        return filename
    except BaseException:
        with suppress(OSError):
            os.remove(filename)
        raise
