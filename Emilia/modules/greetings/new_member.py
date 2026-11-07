from pymongo.errors import PyMongoError
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import RPCError
from pyrogram.types import ChatMemberUpdated, InlineKeyboardMarkup
from redis.exceptions import RedisError

from Emilia.application import LOGGER
from Emilia.database.welcome import (
    DEFAUT_WELCOME,
    GetCleanWelcome,
    GetCleanWelcomeMessage,
    GetWelcome,
    GetWelcomemessageOnOff,
    SetCleanWelcomeMessage,
    get_captcha_policy,
    isWelcome,
)
from Emilia.locales import tr
from Emilia.modules.greetings.captcha import button_captcha, text_captcha
from Emilia.modules.greetings.group_onboarding import send_group_onboarding
from Emilia.services import captcha
from Emilia.utils.auth import is_dev, is_owner
from Emilia.utils.button_gen import button_markdown_parser
from Emilia.utils.chat_status import bot_has_permission, is_user_admin
from Emilia.utils.client_context import bot_id
from Emilia.utils.decorators import leavemute, log_to_channel
from Emilia.utils.logging import log_bot_join
from Emilia.utils.restrictions import restrict_member
from Emilia.utils.welcome_format import DefaultWelcomeFillings
from Emilia.utils.welcome_sender import SendWelcomeMessage


@Client.on_chat_member_updated(filters.group, group=690)
@leavemute
@log_to_channel
async def NewMemeber(client: Client, message: ChatMemberUpdated):
    try:
        if (
            message.new_chat_member
            and message.new_chat_member.status
            not in {
                ChatMemberStatus.BANNED,
                ChatMemberStatus.LEFT,
                ChatMemberStatus.RESTRICTED,
            }
            and (
                not message.old_chat_member
                or message.old_chat_member.status
                in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}
            )
        ):
            pass
        else:
            return

        chat_id = message.chat.id

        if await GetCleanWelcome(chat_id):
            CleanWelcomeMessageID = await GetCleanWelcomeMessage(chat_id)
            if CleanWelcomeMessageID is not None and not await captcha.pending_welcome(
                client, chat_id, CleanWelcomeMessageID
            ):
                try:
                    await client.delete_messages(chat_id=chat_id, message_ids=CleanWelcomeMessageID)
                except (RPCError, OSError) as e:
                    LOGGER.error(f"[Welcome Debug] Failed to delete old welcome message: {e}")

        NewUserJson = message.new_chat_member.user if message.new_chat_member else message.from_user

        user_id = NewUserJson.id

        # Emilia Welcome stuffs
        if user_id == bot_id(client):
            await log_bot_join(client, message)
            if getattr(client, "is_clone", False):
                await client.send_message(
                    chat_id=chat_id,
                    text=tr("new_member.welcome_you_ve_just_added_a_clone"),
                )
                return
            await send_group_onboarding(client, chat_id)
            return

        # Emilia's Special welcome for kami-samas!
        if is_owner(user_id):
            await client.send_message(
                chat_id=chat_id, text=tr("new_member.omfg_the_old_man_s_here_i")
            )
            return "WELCOME_BOT_OWNER", user_id, NewUserJson.first_name

        # Emilia's Special welcome for her onii-chan gang!
        if is_dev(user_id):
            await client.send_message(chat_id=chat_id, text=tr("new_member.onii_chan_is_here_owo"))
            return "WELCOME_DEV", user_id, NewUserJson.first_name

        CaptchaButton = None
        challenge = None
        needs_captcha = False
        completing_join_request = False
        policy = await get_captcha_policy(chat_id, user_id)
        if policy["enabled"]:
            needs_captcha = not await is_user_admin(
                message, user_id=user_id, chat_id=chat_id, silent=True
            ) and (policy["reverify"] or not policy["verified"])
            if needs_captcha:
                completing_join_request = await captcha.verifying_join_request(
                    client, chat_id, user_id
                )
                if completing_join_request:
                    needs_captcha = False
        if needs_captcha and await bot_has_permission(
            message, privileges="can_restrict_members", silent=True
        ):
            try:
                # Restriction invalidates older challenges, so create this one
                # only after the restriction succeeds.
                await restrict_member(chat_id, user_id, client=client)
            except (RPCError, PyMongoError, RedisError, OSError) as e:
                LOGGER.error(f"[Welcome Debug] Failed to restrict user: {e}")
            else:
                mode, label = policy["mode"], policy["label"]
                challenge = await captcha.begin(
                    client,
                    chat_id,
                    user_id,
                    mode,
                    rules=policy["rules"],
                    chat_title=message.chat.title,
                )
                builder = (
                    button_captcha.CaptchaButton if mode == "button" else text_captcha.textCaptcha
                )
                CaptchaButton = await builder(
                    chat_id, user_id, client=client, challenge=challenge, label=label
                )
        else:
            if not completing_join_request:
                await captcha.invalidate(client, chat_id, user_id)
            if needs_captcha:
                await client.send_message(chat_id, tr("new_member.i_haven_t_got_the_rights_to"))

        if not await GetWelcomemessageOnOff(chat_id):
            if CaptchaButton:
                await _send_captcha_prompt(client, chat_id, user_id, CaptchaButton, challenge)
            return
        try:
            if await isWelcome(chat_id):
                Content, Text, DataType = await GetWelcome(chat_id)
                Text, buttons = button_markdown_parser(Text)
                rows = buttons + (CaptchaButton or [])
                reply_markup = InlineKeyboardMarkup(rows) if rows else None
                WelcomeSentMessage = await SendWelcomeMessage(
                    client,
                    message,
                    NewUserJson,
                    Content,
                    Text,
                    DataType,
                    reply_markup=reply_markup,
                )
            else:
                Text = await DefaultWelcomeFillings(message, DEFAUT_WELCOME, NewUserJson)
                reply_markup = InlineKeyboardMarkup(CaptchaButton) if CaptchaButton else None
                WelcomeSentMessage = await client.send_message(
                    chat_id=chat_id, text=Text, reply_markup=reply_markup
                )
            if WelcomeSentMessage is None:
                raise RuntimeError("The welcome message was not sent")
        except Exception as e:
            LOGGER.error(f"[Welcome Debug] Failed to send welcome message: {e}")
            if CaptchaButton:
                await _send_captcha_prompt(client, chat_id, user_id, CaptchaButton, challenge)
            return
        await SetNewMemMessageIDs(client, chat_id, user_id, WelcomeSentMessage, challenge=challenge)
    except Exception as e:
        LOGGER.error(f"[Welcome Debug] Unexpected error in NewMemeber: {e}")


async def _send_captcha_prompt(client, chat_id, user_id, buttons, challenge):
    sent = await client.send_message(
        chat_id, tr("captcha.member_prompt"), reply_markup=InlineKeyboardMarkup(buttons)
    )
    await SetNewMemMessageIDs(client, chat_id, user_id, sent, challenge=challenge)


async def SetNewMemMessageIDs(client, chat_id, user_id, sent, *, challenge=None):
    if challenge:
        if not await captcha.bind_welcome(challenge, sent):
            from Emilia.modules.greetings.utils.actions import remove_captcha_button

            await remove_captcha_button(client, chat_id, sent.id, challenge["token"])
    if await GetCleanWelcome(chat_id):
        await SetCleanWelcomeMessage(chat_id, sent.id)
