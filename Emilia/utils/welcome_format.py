from Emilia.utils.chat_context import effective_chat
from Emilia.utils.message_content import text_value
from Emilia.utils.note_format import context_fields, fill_context_fields, fill_native_context


async def Welcomefillings(message, message_text, NewUserJson):
    if NewUserJson is None:
        return message_text
    count = (
        await message._client.get_chat_members_count(effective_chat(message).id)
        if "{count}" in text_value(message_text)
        else None
    )
    return fill_native_context(
        message_text, NewUserJson, effective_chat(message).title, count=count
    )


async def DefaultWelcomeFillings(message, template, user):
    if user is None:
        return template
    values = context_fields(user, effective_chat(message).title)
    if "{count}" in template:
        values["count"] = str(
            await message._client.get_chat_members_count(effective_chat(message).id)
        )
    return fill_context_fields(template, values)
