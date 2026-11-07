import asyncio
import functools
import math
import time

from PIL import Image
from pymongo.errors import PyMongoError
from pyrogram.enums import ChatType
from pyrogram.errors import RPCError
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from redis.exceptions import RedisError

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command, listen
from Emilia.database import levels as levels_db
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.services.rate_limit import check_limit
from Emilia.utils.admins import get_time
from Emilia.utils.cache import SimpleCache
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker, log_to_channel
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_actor import actor_id, actor_user
from Emilia.utils.rank_card import generate_rank_card_sync

users_collection = db.chatlevels
first_name = db.first_name
level = db.onofflevel

ranks = [
    {"name": "Elf", "min_points": 0},
    {"name": "Oni", "min_points": 500},
    {"name": "Giant", "min_points": 1000},
    {"name": tr("levels.evil_eye"), "min_points": 10000},
    {"name": "Werewolf", "min_points": 50000},
    {"name": "DragonKin", "min_points": 100000},
]

# Configurable constants
XP_BASE = Config.LEVEL_XP_BASE
XP_MULTIPLIER = Config.LEVEL_XP_MULTIPLIER

# helpers


def get_level_from_xp(xp):
    if xp <= 0:
        return 1
    # formula: lvl = (xp/base)^(1/mult)
    return int(((xp / XP_BASE) ** (1 / XP_MULTIPLIER)) + 0.01) + 1


def get_xp_for_level(level, prestige_level=0):
    if level <= 1:
        return 0
    return int(XP_BASE * ((level - 1) ** XP_MULTIPLIER))


def get_progress_bar(current, total, length=10):
    if total <= 0:
        percent = 1.0
    else:
        percent = min(1.0, current / total)
    filled = int(length * percent)
    return "█" * filled + "░" * (length - filled) + f" {int(percent * 100)}%"


# Settings and display names are cached; XP commits directly to MongoDB.
_level_cache = SimpleCache(default_ttl=120, namespace="levels_settings_v2")  # per-chat toggle
_name_cache = SimpleCache(default_ttl=300, namespace="levels_name")  # per-user first_name


def _is_group(message) -> bool:
    return message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def _get_level_settings(chat_id):
    return await _level_cache.get_or_load(
        f"lvl:{chat_id}", lambda: level.find_one({"chat_id": chat_id}, {"_id": 0})
    )


async def _get_level_on(chat_id: int) -> bool:
    settings = await _get_level_settings(chat_id)
    return bool(settings and not settings.get("disabled", False))


async def _get_first_name(user_id: int) -> str:
    key = f"name:{user_id}"
    val = await _name_cache.get(key)
    if val is not None:
        return val
    doc = await first_name.find_one({"user_id": user_id})
    name = (doc or {}).get("first_name") or "Unknown"
    await _name_cache.set(key, name, ttl=300)
    return name


def get_rank(points):
    for rank in ranks[::-1]:
        if points >= rank["min_points"]:
            return rank["name"]
    return "Gay"


async def get_leaderboard(chat_id, limit=10, skip=0):
    # Use Mongo sort + limit
    cursor = (
        users_collection.find({"chat_id": chat_id}, {"_id": 0, "user_id": 1, "points": 1})
        .sort("points", -1)
        .skip(skip)
        .limit(limit)
    )
    return await cursor.to_list(length=limit)


async def get_user_stats(user_id, chat_id):
    user_data = await users_collection.find_one({"user_id": user_id, "chat_id": chat_id})
    if not user_data:
        return None
    points = user_data.get("points", 0)
    first_name1 = await _get_first_name(user_id)

    # Dynamic Level Calculation
    level_val = get_level_from_xp(points)

    # XP Stats
    next_level_xp_total = get_xp_for_level(level_val + 1)
    current_level_xp_start = get_xp_for_level(level_val)

    xp_in_level = points - current_level_xp_start
    xp_needed_level = next_level_xp_total - current_level_xp_start

    if xp_needed_level > 0:
        progress = xp_in_level / xp_needed_level
    else:
        progress = 1.0

    rank = get_rank(points)

    return {
        "points": points,
        "first_name": first_name1,
        "level": level_val,
        "rank": rank,
        "xp_in_level": xp_in_level,
        "xp_needed_level": xp_needed_level,
        "next_level_xp_total": next_level_xp_total,
        "progress": progress,
        "last_date": user_data.get("last_date", 0),
        "streak": user_data.get("streak", 0),
        "prestige": user_data.get("prestige", 0),
        "reputation": user_data.get("reputation", 0),
    }


@command("prestige", chat_scope="group")
async def prestige_handler(client, message):
    if not await _get_level_on(message.chat.id):
        return

    stats = await get_user_stats(
        message.from_user.id if message.from_user else None, message.chat.id
    )
    if not stats:
        return await message.reply_text(tr("levels.register_first"))

    updated = await levels_db.advance_prestige(message.from_user.id, message.chat.id)
    if not updated:
        return await message.reply_text(tr("levels.you_need_to_reach_dragonkin_rank_100"))
    await message.reply_text(
        tr(
            "levels.prestige_advancement_user_prestige_level_xp_has_reset",
            first_name=stats["first_name"],
            prestige=updated["prestige"],
        )
    )


@command(pattern="thanks|rep", chat_scope="group")
async def reputation_handler(client, message):
    if not await _get_level_on(message.chat.id):
        return
    if not message.reply_to_message_id:
        return await reply_usage(message)

    reply_msg = message.reply_to_message
    if not reply_msg:
        return
    reply_sender_id = reply_msg.from_user.id if reply_msg.from_user else None
    if reply_sender_id == (message.from_user.id if message.from_user else None):
        return await message.reply_text(tr("levels.you_can_t_give_rep_to_yourself"))
    if (
        not reply_sender_id
        or getattr(reply_msg.from_user, "is_bot", False)
        or not message.from_user
    ):
        return
    granted, remaining = await levels_db.grant_reputation(
        message.from_user.id, message.chat.id, reply_sender_id
    )
    if not granted:
        return await message.reply_text(
            tr("levels.can_give_rep_again", remaining=get_time(remaining))
        )
    await message.reply_text(
        tr("levels.reputation_awarded", user_name=reply_msg.from_user.first_name)
    )


@command("levelset", chat_scope="group")
@anonadmin_checker
async def levelset_handler(client, message):
    if not actor_user(message):
        return
    if not await _get_level_on(message.chat.id):
        return await message.reply_text(tr("levels.disabled"))
    if not await is_user_admin(
        message, user_id=actor_id(message) if actor_user(message) else None, silent=False
    ):
        return

    args = message.text.split()
    if len(args) < 3:
        return await reply_usage(message)

    cmd = args[1].lower()
    if cmd == "event":
        try:
            mult = float(args[2])
            if not math.isfinite(mult) or not 0.1 <= mult <= 100:
                raise ValueError("Multiplier must be between 0.1 and 100")
            await atomic_upsert(
                level, {"chat_id": message.chat.id}, {"$set": {"event_multiplier": mult}}
            )
            await _level_cache.delete(f"lvl:{message.chat.id}")
            await message.reply_text(tr("levels.event_multiplier_group_set_x", mult=mult))
        except ValueError:
            await message.reply_text(tr("levels.invalid_number"))


@command("leaderboard", chat_scope="group")
async def _leaderboard(client, message):
    if not await _get_level_on(message.chat.id):
        return await message.reply_text(tr("levels.disabled"))
    chat_id = message.chat.id
    # Default page 0
    leaderboard = await get_leaderboard(chat_id, limit=10, skip=0)
    lmao = ""

    if leaderboard:
        lmao += tr("levels.leaderboard_chat")
        for idx, user in enumerate(leaderboard, start=1):
            points = user.get("points", 0)
            user_id = user.get("user_id")
            first_name1 = await _get_first_name(user_id)
            lmao += tr(
                "levels.tg_user_id_points",
                idx=idx,
                first_name1=first_name1,
                user_id=user_id,
                points=points,
            )
        lmao += tr("levels.use_register_setup_names")

        # Buttons
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("levels.global_leaderboard"),
                        callback_data="gleaderboard_",
                    ),
                    InlineKeyboardButton(tr("buttons.next_arrow"), callback_data="chatlb_10"),
                ]
            ]
        )
    else:
        lmao += tr("levels.no_data_chat_try_register_register_yourself_bot")
        buttons = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("levels.global_leaderboard"),
                        callback_data="gleaderboard_",
                    )
                ]
            ]
        )

    await message.reply_text(lmao, reply_markup=buttons)


@callbackquery(pattern=r"chatlb_(\d+)", access=CallbackAccess(public=True))
async def chat_lb_callback(client, query):
    offset = int(query.matches[0].group(1))
    chat_id = query.message.chat.id
    leaderboard = await get_leaderboard(chat_id, limit=10, skip=offset)

    if not leaderboard:
        return await query.answer(tr("levels.no_more_rankings"), show_alert=True)

    lmao = tr("levels.leaderboard_chat")
    for idx, user in enumerate(leaderboard, start=offset + 1):
        points = user.get("points", 0)
        user_id = user.get("user_id")
        first_name1 = await _get_first_name(user_id)
        lmao += tr(
            "levels.tg_user_id_points",
            idx=idx,
            first_name1=first_name1,
            user_id=user_id,
            points=points,
        )

    buttons = []
    if offset >= 10:
        buttons.append(
            InlineKeyboardButton(
                tr("buttons.previous_arrow"), callback_data=f"chatlb_{offset - 10}"
            )
        )
    buttons.append(
        InlineKeyboardButton(tr("buttons.next_arrow"), callback_data=f"chatlb_{offset + 10}")
    )
    await query.edit_message_text(lmao, reply_markup=InlineKeyboardMarkup([buttons]))


@callbackquery(pattern="gleaderboard_", access=CallbackAccess(public=True))
async def gleaderboard(client, query):
    pipeline = [
        {"$group": {"_id": "$user_id", "points": {"$sum": "$points"}}},
        {"$sort": {"points": -1}},
        {"$limit": 10},
    ]
    cursor = await users_collection.aggregate(pipeline)
    rows = await cursor.to_list(length=10)
    sorted_players = [{"user_id": r["_id"], "points": r["points"]} for r in rows]

    # Fetch the first_name for each user using cache
    for player in sorted_players:
        if "user_id" not in player:
            continue
        user_id = player["user_id"]
        player["first_name"] = await _get_first_name(user_id)

    gae = tr("levels.global_leaderboard_gleaderboard")
    for rank, player in enumerate(sorted_players, start=1):
        name = player.get("first_name", "Unknown")
        points = player.get("points", 0)
        gae += tr(
            "levels.tg_user_id_points",
            idx=rank,
            first_name1=name,
            user_id=player.get("user_id", "N/A"),
            points=points,
        )

    await query.edit_message_text(gae)


@command("daily", chat_scope="group")
async def _daily(client, message):
    if not await _get_level_on(message.chat.id):
        return await message.reply_text(tr("levels.disabled"))
    try:
        stats = await get_user_stats(message.from_user.id, message.chat.id)
    except KeyError:
        stats = None
    if not stats:
        return await message.reply_text(tr("levels.use_register_to_register_yourself_in_bot"))
    updated = await levels_db.claim_daily(message.from_user.id, message.chat.id)
    if updated:
        streak = updated["streak"]
        bonus = min(streak * 10, 100)
        return await message.reply_text(
            tr(
                "levels.daily_reward_claimed_computed_streak_bonus_xp_total",
                streak=streak,
                bonus=bonus,
                bonus_2=100 + bonus,
                points=updated["points"],
            )
        )
    current = await get_user_stats(message.from_user.id, message.chat.id) or stats
    remaining = max(0, 86400 - (time.time() - current.get("last_date", 0)))
    await message.reply_text(
        tr("levels.you_can_claim_your_daily_points_in", remaining=get_time(remaining))
    )


@command("weekly", chat_scope="group")
async def _weekly(client, message):
    if not await _get_level_on(message.chat.id):
        return await message.reply_text(tr("levels.disabled"))
    try:
        stats = await get_user_stats(message.from_user.id, message.chat.id)
    except KeyError:
        stats = None
    if not stats:
        return await message.reply_text(tr("levels.use_register_to_register_yourself_in_bot"))
    updated = await levels_db.claim_weekly(message.from_user.id, message.chat.id)
    if updated:
        return await message.reply_text(
            tr(
                "levels.successfully_claimed_weekly_500_points_current_points",
                points=updated["points"],
            )
        )
    current = (
        await users_collection.find_one(
            {"user_id": message.from_user.id, "chat_id": message.chat.id}
        )
        or {}
    )
    remaining = max(0, 7 * 86400 - (time.time() - current.get("last_collection_weekly", 0)))
    await message.reply_text(
        tr("levels.you_can_claim_your_weekly_500_points", remaining=get_time(remaining))
    )


@command("rank", chat_scope="group")
async def rank(client, message):
    if not await _get_level_on(message.chat.id):
        return await message.reply_text(tr("levels.disabled"))
    user_id = message.from_user.id
    chat_id = message.chat.id

    try:
        stats = await get_user_stats(user_id, chat_id)
    except KeyError:
        stats = None

    if stats:
        # Generate Visual Rank Card
        reply_msg = await message.reply_text(tr("levels.generatin_rank_card"))
        try:
            loop = asyncio.get_running_loop()

            # Download profile photo
            try:
                pfp = None
                async for photo in client.get_chat_photos(user_id, limit=1):
                    bio = await client.download_media(photo.file_id, in_memory=True)
                    pfp = bio.getvalue() if bio else None
            except (RPCError, OSError):
                pfp = None

            rank_image = await loop.run_in_executor(
                None,
                functools.partial(
                    generate_rank_card_sync,
                    firstname=stats["first_name"],
                    avatar_bytes=pfp,
                    current_xp=stats["points"],
                    total_xp=stats["next_level_xp_total"],
                    level=stats["level"],
                    rank_name=stats["rank"],
                ),
            )
            rank_image.name = "rank.png"

            bar = get_progress_bar(stats["xp_in_level"], stats["xp_needed_level"])

            caption = tr(
                "levels.level_xp",
                first_name=stats["first_name"],
                rank=stats["rank"],
                level=stats["level"],
                bar=bar,
                points=stats["points"],
                next_level_xp_total=stats["next_level_xp_total"],
            )

            await message.reply_photo(rank_image, caption=caption)
            await reply_msg.delete()
        except (RPCError, OSError, ValueError, Image.DecompressionBombError) as e:
            LOGGER.error(f"Rank generation failed: {e}")
            await reply_msg.edit_text(
                tr(
                    "levels.s_stats_points_level_rank",
                    first_name=stats["first_name"],
                    points=stats["points"],
                    level=stats["level"],
                    rank=stats["rank"],
                )
            )

    else:
        response = tr("levels.use_register_register_name_first")
        await message.reply_text(response)


@command("register", chat_scope="group")
async def register_(client, message):
    if not await _get_level_on(message.chat.id):
        return await message.reply_text(tr("levels.disabled"))

    try:
        args: str = message.text.split(None, 1)[1].strip()
    except IndexError:
        return await message.reply_text(tr("levels.use_it_like_register_pussyslayer69_note_you"))

    if not args or len(args) > 20:
        return await message.reply_text(tr("levels.name_too_long_please_try_a_shorter"))

    result = await levels_db.register_name(message.from_user.id, args)
    if result == "registered":
        return await message.reply_text(tr("levels.you_are_already_registered_please_use_rank"))
    if result == "taken":
        return await message.reply_text(
            tr("levels.has_already_used_someone_else_please_try_some", arguments=args)
        )
    await _name_cache.delete(f"name:{message.from_user.id}")
    return await message.reply_text(
        tr("levels.successfully_registered_use_rank_see_stats", arguments=args)
    )


@command("rankings", chat_scope="private")
async def rankings(client, message):
    response = tr("levels.ranking_system_consists_multiple_ranks_each_name_minimum")
    await message.reply_text(response)


@listen()
async def handle_message(client, message):
    try:
        if not _is_group(message):
            return
        if not message.text:
            return
        if not message.from_user:
            return
        user_id = message.from_user.id
        chat_id = message.chat.id

        if getattr(message.from_user, "is_bot", False):
            return

        if not await _get_level_on(chat_id):
            return

        # Anti-Abuse Checks
        if len(message.text) < 3:
            return  # Too short

        allowed = await check_limit(f"levels:{chat_id}:{user_id}", 1, Config.LEVEL_MESSAGE_COOLDOWN)
        if not allowed.allowed:
            return
        settings = await _get_level_settings(chat_id) or {}
        awarded = await levels_db.award_message_points(
            user_id, chat_id, settings.get("event_multiplier", Config.LEVEL_EVENT_MULTIPLIER)
        )
        if awarded is None:
            return
        old_pts, new_pts = awarded["old_points"], awarded["points"]
        for r in ranks[::-1]:
            if old_pts < r["min_points"] <= new_pts:
                await message.reply_text(
                    tr(
                        "levels.congratulations_reaching_new_rank_check_rank_know_stats",
                        name=r["name"],
                    )
                )
                break
    except (RPCError, PyMongoError, RedisError, OSError):
        LOGGER.exception("levels handle_message failed")


ON_ARG = ["on", "yes", "true", 1, "enable"]
OFF_ARG = ["off", "no", "false", 0, "disable"]


@command("level", chat_scope="group")
@anonadmin_checker
@log_to_channel
async def levelonoff(client, message):
    if not await is_user_admin(
        message, user_id=actor_id(message) if actor_user(message) else None, silent=False
    ):
        return

    key = f"lvl:{message.chat.id}"
    check = message.text.split()
    try:
        if check[1] in ON_ARG:
            doc = await level.find_one({"chat_id": message.chat.id})
            if doc and not doc.get("disabled", False):
                return await message.reply_text(
                    tr("levels.level_system_is_already_enabled_in_this")
                )
            await atomic_upsert(
                level,
                {"chat_id": message.chat.id},
                {"$set": {"chat_id": message.chat.id}, "$unset": {"disabled": ""}},
            )
            await _level_cache.delete(key)
            await message.reply_text(tr("levels.level_system_enabled"))
            return "LEVEL_ON", None, None
        elif check[1] in OFF_ARG:
            doc = await level.find_one({"chat_id": message.chat.id})
            if not doc or doc.get("disabled", False):
                return await message.reply_text(
                    tr("levels.level_system_is_already_disabled_in_this")
                )
            # Instead of deleting, just mark as disabled
            await atomic_upsert(level, {"chat_id": message.chat.id}, {"$set": {"disabled": True}})
            await _level_cache.delete(key)
            await message.reply_text(tr("levels.level_system_disabled"))
            return "LEVEL_OFF", None, None
        else:
            await message.reply_text(tr("levels.invalid_argument"))
            return
    except IndexError:
        doc = await level.find_one({"chat_id": message.chat.id})
        if doc and not doc.get("disabled", False):
            await message.reply_text(tr("levels.level_system_in_enabled_in_this_chat"))
        else:
            await message.reply_text(tr("levels.level_system_in_disabled_in_this_chat"))
