from datetime import UTC, datetime

from pyrogram.types import ChatPermissions


async def restrict_member(
    chat_id: int,
    user_id: int,
    *,
    can_send_messages: bool = False,
    until_date: int | datetime | None = None,
    client,
    permissions: ChatPermissions | None = None,
):
    if not can_send_messages:
        from Emilia.services.captcha import invalidate

        await invalidate(client, chat_id, user_id)
    if permissions is None:
        permissions = ChatPermissions(
            can_send_messages=can_send_messages,
            can_send_audios=can_send_messages,
            can_send_documents=can_send_messages,
            can_send_photos=can_send_messages,
            can_send_videos=can_send_messages,
            can_send_video_notes=can_send_messages,
            can_send_voice_notes=can_send_messages,
            can_send_other_messages=can_send_messages,
            can_send_polls=can_send_messages,
            can_add_web_page_previews=can_send_messages,
            can_react_to_messages=can_send_messages,
        )
    if isinstance(until_date, int):
        until_date = datetime.fromtimestamp(until_date, UTC)
    return await client.restrict_chat_member(chat_id, user_id, permissions, until_date=until_date)
