import random
from datetime import UTC, datetime, timedelta

from pymongo.errors import PyMongoError
from pyrogram.errors import RPCError

from Emilia.application import LOGGER, db
from Emilia.custom_filter import command
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr

collection = db.coup


async def select_couples(client, chat_id):
    try:
        members = []
        async for member in client.get_chat_members(chat_id):
            if not member.user.is_bot:
                members.append(member.user.id)

        if len(members) < 2:
            await client.send_message(chat_id, tr("shippering.oops_we_need_at_least_two_members"))
            return

        couple_a, couple_b = random.sample(members, 2)
        current_time = datetime.now(UTC)
        expiration_time = current_time + timedelta(hours=24)

        await atomic_upsert(
            collection,
            {"chat_id": chat_id},
            {
                "$set": {
                    "couple_a": int(couple_a),
                    "couple_b": int(couple_b),
                    "expiration_time": expiration_time,
                }
            },
        )

        couple_a_user = await client.get_users(couple_a)
        couple_b_user = await client.get_users(couple_b)

        couple_a_mention = (
            couple_a_user.mention if couple_a_user else tr("shippering.user_not_found")
        )
        couple_b_mention = (
            couple_b_user.mention if couple_b_user else tr("shippering.user_not_found")
        )

        await client.send_message(
            chat_id,
            tr(
                "shippering.new_couples_have_been_selected_they_re",
                couple_a_mention=couple_a_mention,
                couple_b_mention=couple_b_mention,
            ),
        )

    except (RPCError, PyMongoError, OSError):
        LOGGER.exception("Couple selection failed")
        await client.send_message(
            chat_id,
            tr("shippering.something_went_wrong"),
        )


async def get_couples(chat_id):
    return await collection.find_one({"chat_id": chat_id})


@command("couples", disable=True, chat_scope="group")
async def choose_couples_command(client, message):
    chat_id = message.chat.id

    couple_data = await get_couples(chat_id)
    now = datetime.now(UTC)
    expires_at = (couple_data or {}).get("expiration_time")
    if isinstance(expires_at, datetime) and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if isinstance(expires_at, datetime) and expires_at > now:
        couple_a_id = couple_data.get("couple_a")
        couple_b_id = couple_data.get("couple_b")

        couple_a = await get_user_or_not_found(client, couple_a_id)
        couple_b = await get_user_or_not_found(client, couple_b_id)
        if couple_a is None or couple_b is None:
            await select_couples(client, chat_id)
            return
        hours_left = int((expires_at - now).total_seconds() // 3600)
        await client.send_message(
            chat_id,
            tr(
                "shippering.couple_day_hours_left_until_next_selection",
                user_name=couple_a.first_name,
                user_name_2=couple_b.first_name,
                hours_left=hours_left,
            ),
        )

    else:
        await select_couples(client, chat_id)


async def get_user_or_not_found(client, user_id):
    try:
        user = await client.get_users(user_id)
        return user
    except (RPCError, OSError) as e:
        LOGGER.error(f"Error retrieving user: {e}")
        return None
