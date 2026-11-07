import html

from Emilia.custom_filter import command
from Emilia.database.warnings import get_warn_mode, warn_limit
from Emilia.locales import tr
from Emilia.modules.warnings.set_warn_mode import WarnModeMap
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.decorators import anonadmin_checker


def warn_mode_map(warn_mode_in):
    warn_mode_raw = WarnModeMap(warn_mode_in)
    warn_mode_out = warn_mode_raw.name
    return warn_mode_out


@command("warnings", disable=True, chat_scope="group", allow_connected=True)
@anonadmin_checker
async def warnings(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await is_user_admin(message):
        return

    warn_chat_limit = await warn_limit(chat_id)
    text = tr(
        "warnings.there_warning_limit",
        warn_chat_limit=warn_chat_limit,
        chat_title=html.escape(chat_title),
    )
    warn_mode_in, warn_mode_time = await get_warn_mode(chat_id)
    warn_mode = warn_mode_map(warn_mode_in)
    if warn_mode == "Ban":
        text += tr("warnings.when_limit_has_exceeded_user_will_banned")
    elif warn_mode == "Kick":
        text += tr("warnings.when_limit_has_exceeded_user_will_kicked")
    elif warn_mode == "Mute":
        text += tr("warnings.when_limit_has_exceeded_user_will_muted")
    elif warn_mode == "Tmute":
        text += tr("warnings.when_limit_has_exceeded_user_will_temporarily_muted")
    elif warn_mode == "Tban":
        text += tr("warnings.when_limit_has_exceeded_user_will_temporarily_banned")

    await message.reply(text)
