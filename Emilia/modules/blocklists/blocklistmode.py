import html
from enum import Enum, auto

from Emilia.custom_filter import command
from Emilia.database.blocklists import getblocklistmode, setblocklistmode
from Emilia.locales import tr
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import check_admins
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.time import convert_time, get_time, time_string_helper


class BlocklistModeMap(Enum):
    nothing = auto()
    ban = auto()
    mute = auto()
    kick = auto()
    warn = auto()
    tban = auto()
    tmute = auto()


@command(["blocklistmode", "blacklistmode"], allow_connected=True, chat_scope="group")
@anonadmin_checker
async def blocklistmode(client, message):
    chat_id = effective_chat_id(message)
    chat_title = effective_chat(message).title

    if not await check_admins(message, privileges="can_restrict_members"):
        return

    if len(message.text.split()) >= 2:
        args = message.text.split()[1]

        if args == "nothing":
            blocklist_mode = BlocklistModeMap.nothing.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                tr(
                    "blocklistmode.ve_updated_blocklist_action_nothing_users_who_say",
                    chat_title=html.escape(chat_title),
                )
            )

        elif args == "ban":
            blocklist_mode = BlocklistModeMap.ban.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                tr(
                    "blocklistmode.ve_updated_blocklist_action_ban_users_who_say",
                    chat_title=html.escape(chat_title),
                )
            )

        elif args == "mute":
            blocklist_mode = BlocklistModeMap.mute.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                tr(
                    "blocklistmode.ve_updated_blocklist_aaction_mute_users_who_say",
                    chat_title=html.escape(chat_title),
                )
            )

        elif args == "kick":
            blocklist_mode = BlocklistModeMap.kick.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                tr(
                    "blocklistmode.ve_updated_blocklist_action_kick_users_who_say",
                    chat_title=html.escape(chat_title),
                )
            )

        elif args == "warn":
            blocklist_mode = BlocklistModeMap.warn.value
            await setblocklistmode(chat_id, blocklist_mode)
            await message.reply(
                tr(
                    "blocklistmode.ve_updated_blocklist_action_warn_users_who_say",
                    chat_title=html.escape(chat_title),
                )
            )

        elif args == "tban":
            blocklist_mode = BlocklistModeMap.tban.value
            time_args = await get_time(message, argument_index=2)
            if time_args is None:
                return
            cal_time = convert_time(int(time_args[:-1]), time_args[-1])
            time_limit, time_format = time_string_helper(time_args)
            await setblocklistmode(chat_id, blocklist_mode, blocklist_time=cal_time)
            await message.reply(
                tr(
                    "blocklistmode.ve_updated_blocklist_action_tban_users_who_say",
                    chat_title=html.escape(chat_title),
                    time_limit=time_limit,
                    time_format=time_format,
                    time_limit_2=time_limit,
                    time_format_2=time_format,
                )
            )

        elif args == "tmute":
            blocklist_mode = BlocklistModeMap.tmute.value
            time_args = await get_time(message, argument_index=2)
            if time_args is None:
                return
            cal_time = convert_time(int(time_args[:-1]), time_args[-1])
            time_limit, time_format = time_string_helper(time_args)
            await setblocklistmode(chat_id, blocklist_mode, blocklist_time=cal_time)
            await message.reply(
                tr(
                    "blocklistmode.ve_updated_blocklist_action_tmute_users_who_say",
                    chat_title=html.escape(chat_title),
                    time_limit=time_limit,
                    time_format=time_format,
                    time_limit_2=time_limit,
                    time_format_2=time_format,
                )
            )

        else:
            await message.reply(
                tr("blocklistmode.son_t_recognize_argument_please_use_one_nothing", arguments=args)
            )
    else:
        (
            blocklist_mode,
            blocklist_time,
            blocklist_default_reason,
        ) = await getblocklistmode(chat_id)

        if blocklist_mode == 1:
            text = tr(
                "blocklistmode.current_blocklist_preference_just_delete_messages_blocklisted_words"
            )

        elif blocklist_mode == 2:
            text = tr(
                "blocklistmode.current_blocklist_preference_ban_users_messages_containing_blocklisted"
            )

        elif blocklist_mode == 3:
            text = tr(
                "blocklistmode.current_blocklist_preference_mute_users_messages_containing_blocklisted"
            )

        elif blocklist_mode == 4:
            text = tr(
                "blocklistmode.current_blocklist_preference_kick_users_messages_containing_blocklisted"
            )

        elif blocklist_mode == 5:
            text = tr(
                "blocklistmode.current_blocklist_preference_warn_users_messages_containing_blocklisted"
            )

        elif blocklist_mode == 6:
            text = tr(
                "blocklistmode.current_blocklist_preference_tban_users_messages_containing_blocklisted"
            )

        elif blocklist_mode == 7:
            text = tr("blocklistmode.temporary_mute_setting")

        await message.reply(
            tr(
                "blocklistmode.if_want_change_setting_will_need_specify_action",
                current_setting=text,
            )
        )
