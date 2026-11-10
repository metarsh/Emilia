from Emilia.utils.message_content import FormattedText
from Emilia.utils.saved_message import SavedMessageType, parse_saved_message


def GetWelcomeMessage(message, *, use_inline_text=False):
    if not use_inline_text:
        return parse_saved_message(message, named=False)

    raw = message.text or message.caption or ""
    fields = raw.split(None, 1)
    body = fields[1] if len(fields) > 1 else ""
    entities = (message.entities if message.text else message.caption_entities) or []
    document = FormattedText(raw, entities).slice(len(raw) - len(body)) if body else None
    if document is None and message.reply_to_message:
        return parse_saved_message(message, named=False)

    source = message.reply_to_message or message
    for kind in SavedMessageType:
        if kind is SavedMessageType.text:
            continue
        media = getattr(source, kind.name, None)
        if media is not None:
            return media.file_id, (document or FormattedText("")).record(), kind.value
    if document is not None:
        return None, document.record(), SavedMessageType.text.value
    return parse_saved_message(message, named=False)
