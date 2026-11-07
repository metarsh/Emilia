from html import escape

from pyrogram.enums import ChatType


def message_reference(message, label: str, *, html=False) -> str:
    link = message.link if message.chat.type in (ChatType.SUPERGROUP, ChatType.CHANNEL) else None
    if html:
        return (
            f'<a href="{escape(link, quote=True)}">{escape(label)}</a>' if link else escape(label)
        )
    return f"[{label}]({link})" if link else label
