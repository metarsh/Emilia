from pyrogram import Client, filters

from Emilia.custom_filter import command
from Emilia.database.karma import increase_points, is_karma_on, karma_off, karma_on
from Emilia.locales import tr
from Emilia.utils.chat_status import check_user
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.message_actor import actor_user

regex_upvote = (
    r"(?i)^(\+|\+\+|\+1|thx|tnx|ty|thank you|thanx|thanks|pro|cool|good|👍|nice|noice|piro)$"
)
regex_downvote = r"(?i)^(\-|\-\-|\-1|👎|noob|gross|fuck off)$"

karma_positive_group = 30
karma_negative_group = 40


@command("karma", chat_scope="group")
@anonadmin_checker
@log_to_channel
async def karma_state(_, message):
    if not await check_user(message, privileges="can_change_info"):
        return
    if len(message.text.split()) != 2:
        await reply_usage(message, karma_state)
        return
    chat_id = message.chat.id
    state = message.text.split(None, 1)[1].strip()
    state = state.lower()
    if state == "enable":
        await karma_on(chat_id)
        await message.reply_text(tr("karma.enabled_karma_system_for_this_chat"))
        return "KARMA_ENABLE", None, None
    elif state == "disable":
        await karma_off(chat_id)
        await message.reply_text(tr("karma.disabled_karma_system_for_this_chat"))
        return "KARMA_DISABLE", None, None
    else:
        await reply_usage(message, karma_state)


async def _vote(message, points):
    chat_id = message.chat.id
    if not await is_karma_on(chat_id):
        return
    recipient = actor_user(message.reply_to_message)
    voter = actor_user(message)
    if not recipient or not voter or recipient.id == voter.id:
        return
    total = await increase_points(recipient.id, chat_id, points)
    key = (
        "karma.incremented_karma_1_total_points"
        if points > 0
        else "karma.decremented_karma_1_total_points"
    )
    await message.reply_text(tr(key, user_name=recipient.mention, points=total))


@Client.on_message(
    filters.text
    & filters.group
    & filters.incoming
    & filters.reply
    & filters.regex(regex_upvote)
    & ~filters.via_bot
    & ~filters.bot,
    group=karma_positive_group,
)
async def upvote(_, message):
    await _vote(message, 1)


@Client.on_message(
    filters.text
    & filters.group
    & filters.incoming
    & filters.reply
    & filters.regex(regex_downvote)
    & ~filters.via_bot
    & ~filters.bot,
    group=karma_negative_group,
)
async def downvote(_, message):
    await _vote(message, -1)
