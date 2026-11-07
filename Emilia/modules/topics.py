from pyrogram.enums import ButtonStyle
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.application import LOGGER
from Emilia.custom_filter import callbackquery, command
from Emilia.locales import tr
from Emilia.utils.cb_token import stash, unstash
from Emilia.utils.chat_status import check_user
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.errors import telegram_error_text
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_id, actor_user

ACTION_VERBS = {
    "close": ("Close", "closed"),
    "delete": ("Delete", "deleted"),
    "open": ("Reopen", "reopened"),
}


def _get_args_text(message):
    parts = (message.text or message.caption or "").split(None, 1)
    return parts[1].strip() if len(parts) > 1 else None


def _detect_topic_id(message):
    for candidate in (message, message.reply_to_message):
        if candidate is None:
            continue
        if candidate.topic:
            return candidate.topic.id
        if candidate.reply_to_top_message_id:
            return candidate.reply_to_top_message_id
        if candidate.forum_topic_created:
            return candidate.id
    return None


async def _send_topic_picker(client, message, action: str):
    verb, _ = ACTION_VERBS[action]
    want_closed = action == "open"
    topics = [
        t
        async for t in client.get_forum_topics(message.chat.id)
        if t.id != 1 and t.is_closed == want_closed
    ]
    if not topics:
        state = "closed" if want_closed else "open"
        return await message.reply_text(tr("topics.no_topics_found", state=state))

    buttons = [
        [InlineKeyboardButton(f"{verb}: {t.title}"[:64], callback_data=f"topicact:{action}:{t.id}")]
        for t in topics
    ]
    await message.reply_text(
        tr("topics.run_this_inside_the_topic_to_auto", verb=verb.lower()),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def _run_topic_action(client, chat_id: int, topic_id: int, action: str):
    if action == "close":
        await client.close_forum_topic(chat_id, topic_id)
    elif action == "delete":
        await client.delete_forum_topic(chat_id, topic_id)
    elif action == "open":
        # kurigram has no reopen_forum_topic; edit with closed=False
        await client.edit_forum_topic(chat_id, topic_id, closed=False)


@command("newtopic", chat_scope="group")
@anonadmin_checker
@log_to_channel
async def create_topic(client, message):

    user_id = actor_id(message) if actor_user(message) else None
    if not await check_user(message, user_id=user_id, privileges="can_manage_topics"):
        return

    name = _get_args_text(message)
    if not name:
        return await reply_usage(message, create_topic)

    if message.chat.is_forum:
        topic = await client.create_forum_topic(message.chat.id, name)
        await message.reply_text(tr("topics.successfully_created_id", name=name, topic_id=topic.id))
        await client.send_message(
            message.chat.id,
            tr("topics.congratulations_created_successfully_id", name=name, topic_id=topic.id),
            message_thread_id=topic.id,
        )
        return "NEW_TOPIC", None, None
    else:
        return await message.reply_text(tr("errors.forum_required"))


async def _topic_action_command(client, message, action: str, register_result: str):
    user_id = message.from_user.id if message.from_user else None
    if not await check_user(message, user_id=user_id, privileges="can_manage_topics"):
        return

    if not message.chat.is_forum:
        return await message.reply_text(tr("errors.forum_required"))

    text_arg = _get_args_text(message)
    topic_id = None
    if text_arg:
        try:
            topic_id = int(text_arg)
        except (ValueError, TypeError):
            topic_id = None
    if topic_id is None:
        topic_id = _detect_topic_id(message)
    if topic_id is None:
        # No id could be inferred - the ID-based flow is scripting/automation
        # only; the actual UX is picking the topic from a button list.
        await _send_topic_picker(client, message, action)
        return

    await _run_topic_action(client, message.chat.id, topic_id, action)
    return register_result, None, None


@command("deletetopic", chat_scope="group")
@anonadmin_checker
@log_to_channel
async def delete_topic(client, message):
    return await _topic_action_command(client, message, "delete", "DELETE_TOPIC")


@command("closetopic", chat_scope="group")
@anonadmin_checker
@log_to_channel
async def close_topic(client, message):
    return await _topic_action_command(client, message, "close", "CLOSED_TOPIC")


@command("opentopic", chat_scope="group")
@anonadmin_checker
@log_to_channel
async def open_topic(client, message):
    return await _topic_action_command(client, message, "open", "OPENED_TOPIC")


@callbackquery(
    pattern=r"topicact:(close|delete|open):(\d+)",
    access=CallbackAccess(
        chat_id=lambda client, query: query.message.chat.id,
        privilege="can_manage_topics",
        denial="permissions.manage_topics_required",
    ),
)
async def _topic_action_cb(client, query):
    action = query.matches[0].group(1)
    topic_id = int(query.matches[0].group(2))
    _, past = ACTION_VERBS[action]
    try:
        await _run_topic_action(client, query.message.chat.id, topic_id, action)
    except (RPCError, OSError) as exc:
        LOGGER.exception("Topic %s failed in chat %s", action, query.message.chat.id)
        return await query.answer(telegram_error_text(exc) or tr("topics.failed"), show_alert=True)
    await query.answer(tr("topics.topic", past=past))
    await query.message.edit_text(tr("topics.topic_topic_action_cb", topic_id=topic_id, past=past))


@command("renametopic", chat_scope="group")
@anonadmin_checker
@log_to_channel
async def rename_topic(client, message):

    user_id = actor_id(message) if actor_user(message) else None
    if not await check_user(message, user_id=user_id, privileges="can_manage_topics"):
        return

    new_name = _get_args_text(message)
    if not new_name:
        return await reply_usage(message)

    if message.chat.is_forum:
        topic_id = _detect_topic_id(message)
        if topic_id is None:
            try:
                if "|" in new_name:
                    parts = [p.strip() for p in new_name.split("|", 1)]
                    if len(parts) == 2:
                        new_name, maybe_id = parts
                        topic_id = int(maybe_id)
            except ValueError:
                topic_id = None
        if topic_id is None:
            topics = [t async for t in client.get_forum_topics(message.chat.id) if t.id != 1]
            if not topics:
                return await message.reply_text(tr("topics.no_topics_found_to_rename"))
            prompt = await message.reply_text(
                tr("topics.pick_topic_rename", new_name=new_name),
            )
            token = await stash(
                {"name": new_name, "topics": [t.id for t in topics]},
                ttl=300,
                client=client,
                user_id=user_id,
                chat_id=prompt.chat.id,
                message_id=prompt.id,
            )
            buttons = [
                [InlineKeyboardButton(t.title[:64], callback_data=f"topicrenpick:{t.id}:{token}")]
                for t in topics
            ]
            await prompt.edit_reply_markup(InlineKeyboardMarkup(buttons))
            return

        result = await client.edit_forum_topic(message.chat.id, topic_id, title=new_name)
        if result:
            await message.reply_text(tr("topics.successfully_renamed_topic", new_name=new_name))
            return "RENAMED_TOPIC", None, None
        else:
            return await message.reply_text(tr("topics.failed_to_rename_the_topic"))
    else:
        return await message.reply_text(tr("errors.forum_required"))


@callbackquery(
    pattern=r"^topicrenpick:(\d+):([A-Za-z0-9_-]{16})$",
    access=CallbackAccess(
        chat_id=lambda client, query: query.message.chat.id,
        privilege="can_manage_topics",
        denial="permissions.manage_topics_required",
    ),
)
async def _topic_rename_pick_cb(client, query):
    user_id = query.from_user.id
    topic_id = int(query.matches[0].group(1))
    context = {
        "client": client,
        "user_id": user_id,
        "chat_id": query.message.chat.id,
        "message_id": query.message.id,
    }
    data = await unstash(query.matches[0].group(2), **context)
    if not isinstance(data, dict) or topic_id not in data.get("topics", []):
        return await query.answer(
            tr("topics.this_rename_request_expired_run_renametopic_again"),
            show_alert=True,
        )

    if await unstash(query.matches[0].group(2), consume=True, **context) is None:
        return await query.answer(
            tr("topics.this_rename_request_expired_run_renametopic_again"),
            show_alert=True,
        )
    new_name = data["name"]
    try:
        await client.edit_forum_topic(query.message.chat.id, topic_id, title=new_name)
    except (RPCError, OSError) as exc:
        LOGGER.exception("Topic rename failed in chat %s", query.message.chat.id)
        return await query.answer(
            telegram_error_text(exc) or tr("topics.failed_rename"), show_alert=True
        )
    await query.answer(tr("topics.renamed"))
    await query.message.edit_text(tr("topics.topic_renamed", new_name=new_name))


@command("topics", chat_scope="group")
@anonadmin_checker
async def list_topics(client, message):

    user_id = actor_id(message) if actor_user(message) else None
    if not await check_user(message, user_id=user_id, privileges="can_manage_topics"):
        return

    if not message.chat.is_forum:
        return await message.reply_text(tr("errors.forum_required"))

    open_topics = [
        t async for t in client.get_forum_topics(message.chat.id) if not t.is_closed and t.id != 1
    ]
    if not open_topics:
        return await message.reply_text(tr("topics.no_open_topics_to_manage"))

    buttons = [
        [
            InlineKeyboardButton(f"{t.title}"[:40], callback_data=f"topicnoop:{t.id}"),
            InlineKeyboardButton(
                tr("buttons.close"),
                callback_data=f"topicact:close:{t.id}",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                tr("buttons.delete"),
                callback_data=f"topicact:delete:{t.id}",
                style=ButtonStyle.DANGER,
            ),
        ]
        for t in open_topics
    ]
    await message.reply_text(
        tr("topics.open_topics_tap_close_delete_to_manage"),
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@callbackquery(pattern=r"topicnoop:(.*)", access=CallbackAccess(public=True))
async def _topic_noop_cb(client, query):
    await query.answer()
