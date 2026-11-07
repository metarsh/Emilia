from pyrogram.errors import RPCError
from pyrogram.types import LinkPreviewOptions

from Emilia.application import LOGGER
from Emilia.custom_filter import command
from Emilia.locales import tr
from Emilia.utils.forward_origin import fwd_chat
from Emilia.utils.get_user import get_user_id


@command("id", disable=True)
async def getid(client, message):
    chat = message.chat

    if message.sender_chat:
        your_id = message.sender_chat.id
    else:
        your_id = message.from_user.id

    message_id = message.id
    reply = message.reply_to_message

    if message.link:
        text = tr("ids.message_id", link=message.link, message_id=message_id)
    else:
        text = tr("ids.message_id_getid", message_id=message_id)

    text += tr("ids.id_tg_user_id", your_id=your_id, your_id_2=your_id)

    # Check if there are arguments to resolve a specific user
    text_content = message.text or ""
    has_args = len(text_content.split()) >= 2
    if not has_args and message.entities:
        for ent in message.entities:
            if ent.offset > 0:
                has_args = True
                break

    if has_args:
        try:
            user_info = await get_user_id(message)
            if user_info:
                user_id = user_info.id
                u_name = (
                    getattr(user_info, "username", None)
                    or getattr(user_info, "first_name", None)
                    or getattr(user_info, "title", "")
                )
                text += tr("ids.user_id_tg_user_id", user_id=user_id, user_id_2=user_id)
                if u_name:
                    text += f" ({u_name})"
                text += "\n"

        except IndexError:
            pass

        except (RPCError, OSError, ValueError) as e:
            LOGGER.error(e)
            return await message.reply_text(
                tr("ids.could_not_find_a_user_by_this"),
            )

    chat_name = chat.title or chat.first_name or ""
    if chat.username:
        text += tr("ids.chat_id_getid", username=chat.username, chat_id=chat.id)
    else:
        text += tr("ids.chat_id", chat_id=chat.id)
    if chat_name:
        text += f" ({chat_name})"
    text += "\n\n"

    if (
        not getattr(reply, "empty", True)
        and not fwd_chat(message)
        and not reply.sender_chat
        and not message.reply_to_message.new_chat_members
    ):
        if reply.link:
            text += tr("ids.replied_message_id_getid", link=reply.link, message_id=reply.id)
        else:
            text += tr("ids.replied_message_id", message_id=reply.id)

        reply_user = reply.from_user
        if reply_user:
            ru_name = reply_user.username or reply_user.first_name or ""
            text += tr(
                "ids.replied_user_id_tg_user_id", user_id=reply_user.id, user_id_2=reply_user.id
            )
            if ru_name:
                text += f" ({ru_name})"
            text += "\n\n"

    reply_fwd_chat = reply and fwd_chat(reply)
    if reply_fwd_chat:
        fwd_name = reply_fwd_chat.title or reply_fwd_chat.first_name or ""
        text += tr(
            "ids.forwarded_channel_chat_has_id", fwd_name=fwd_name, chat_id=reply_fwd_chat.id
        )

    if reply and reply.sender_chat:
        sender_name = reply.sender_chat.title or reply.sender_chat.first_name or ""
        text += tr("ids.id_replied_chat_channel", chat_id=reply.sender_chat.id)
        if sender_name:
            text += f" ({sender_name})"
        text += "\n"

    if reply and message.reply_to_message.new_chat_members:
        for x in message.reply_to_message.new_chat_members:
            meow = x.id
            meow_name = x.username or x.first_name or getattr(x, "title", "")
            text += tr("ids.added_user_has_id", meow=meow)
            if meow_name:
                text += f" ({meow_name})"
            text += "\n"

    if reply and reply.sticker:
        text += tr("ids.sticker_id", file_id=reply.sticker.file_id)

    if reply and reply.animation:
        text += tr("ids.gif_id", file_id=reply.animation.file_id)

    if reply and reply.audio:
        text += tr("ids.audio_id", file_id=reply.audio.file_id)

    if reply and reply.document:
        text += tr("ids.document_id", file_id=reply.document.file_id)

    if reply and reply.photo:
        text += tr("ids.photo_id", file_id=reply.photo.file_id)

    if reply and reply.video:
        text += tr("ids.video_id", file_id=reply.video.file_id)

    if reply and reply.voice:
        text += tr("ids.voice_id", file_id=reply.voice.file_id)

    if reply and getattr(reply, "video_note", None):
        text += tr("ids.video_note_id", file_id=reply.video_note.file_id)

    await message.reply_text(text, link_preview_options=LinkPreviewOptions(is_disabled=True))
