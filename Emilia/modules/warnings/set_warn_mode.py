import html
from enum import Enum, auto

from pyrogram.enums import ChatType

from Emilia.custom_filter import command
from Emilia.database.warnings import set_warn_mode_db
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import is_bot_admin, user_has_permission
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.time import convert_time, get_time, time_string_helper


class WarnModeMap(Enum):
    Ban = auto()
    Kick = auto()
    Mute = auto()
    Tban = auto()
    Tmute = auto()


@command(["setwarnmode", "warnmode"], chat_scope="group", allow_connected=True)
@anonadmin_checker
async def set_warn_mode(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await user_has_permission(message, privileges="can_restrict_members", silent=False):
        return

    if not await is_bot_admin(message, silent=True):
        return await message.reply(
            tr(
                "set_warn_mode.am_not_admin_which_want_set_different_warn",
                chat_title=html.escape(chat_title),
            )
        )

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]
        if (
            args in {"mute", "tban", "tmute"}
            and effective_chat(message).type != ChatType.SUPERGROUP
        ):
            return await message.reply_text(tr("errors.supergroup_only"))

        if args == "ban":
            warn_mode_map = WarnModeMap.Ban.value
            await set_warn_mode_db(chat_id, warn_mode_map, time=None)
            await message.reply(tr("set_warn_mode.updated_warning_mode_to_banned"))

        elif args == "kick":
            warn_mode_map = WarnModeMap.Kick.value
            await set_warn_mode_db(chat_id, warn_mode_map, time=None)
            await message.reply(tr("set_warn_mode.updated_warning_mode_to_kicked"))

        elif args == "mute":
            warn_mode_map = WarnModeMap.Mute.value
            await set_warn_mode_db(chat_id, warn_mode_map, time=None)
            await message.reply(tr("set_warn_mode.updated_warning_mode_to_muted"))

        elif args == "tban":
            warn_mode_map = WarnModeMap.Tban.value
            time_args = await get_time(message, argument_index=2)
            if time_args is None:
                return
            cal_time = convert_time(int(time_args[:-1]), time_args[-1])
            time_limit, time_format = time_string_helper(time_args)
            await set_warn_mode_db(chat_id, warn_mode_map, time=cal_time)
            await message.reply(
                tr(
                    "set_warn_mode.updated_warning_mode_to_temporarily_banned_for",
                    time_limit=time_limit,
                    time_format=time_format,
                )
            )

        elif args == "tmute":
            warn_mode_map = WarnModeMap.Tmute.value
            time_args = await get_time(message, argument_index=2)
            if time_args is None:
                return
            cal_time = convert_time(int(time_args[:-1]), time_args[-1])
            time_limit, time_format = time_string_helper(time_args)
            await set_warn_mode_db(chat_id, warn_mode_map, time=cal_time)
            await message.reply(
                tr(
                    "set_warn_mode.updated_warning_mode_to_temporarily_muted_for",
                    time_limit=time_limit,
                    time_format=time_format,
                )
            )

        else:
            await message.reply(
                tr("set_warn_mode.don_t_recognize_argument_please_use_one_ban", arguments=args)
            )
    else:
        await reply_usage(message, set_warn_mode)
        return
