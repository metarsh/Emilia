from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.message_content import replace_content, text_value


def strip_note_tags(text):
    for tag in ("{private}", "{noprivate}", "{admin}"):
        text = replace_content(text, tag, "")
    return text


async def privateNote_and_admin_checker(message, text: str, *, chat_id=None):
    privateNote = True
    if "{noprivate}" in text_value(text):
        text = replace_content(text, "{noprivate}", "")
        privateNote = False
    elif "{private}" in text_value(text):
        text = replace_content(text, "{private}", "")
        privateNote = True
    else:
        privateNote = None

    allow = True
    if "{admin}" in text_value(text):
        text = replace_content(text, "{admin}", "")
        if not await is_user_admin(message, chat_id=chat_id, silent=True):
            allow = False
        else:
            allow = True

    return (privateNote, allow)


def preview_text_replace(text):
    if "{preview}" in text_value(text):
        text = replace_content(text, "{preview}", "")
        preview = False
    else:
        preview = True

    return (preview, text)
