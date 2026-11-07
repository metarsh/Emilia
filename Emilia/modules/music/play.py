import asyncio
import html
import logging
import os
import random
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ntgcalls import BaseRTCException, ConnectionNotFound
from pyrogram import Client, filters
from pyrogram.enums import ButtonStyle, ChatMemberStatus, ParseMode
from pyrogram.errors import (
    ChannelPrivate,
    ChatAdminRequired,
    FloodWait,
    GroupcallForbidden,
    GroupCallInvalid,
    InviteRequestSent,
    PeerIdInvalid,
    RPCError,
    UserAlreadyParticipant,
    UserBannedInChannel,
    UserChannelsTooMuch,
    UserNotParticipant,
)
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    LinkPreviewOptions,
    Message,
)
from pytgcalls.exceptions import (
    CallBusy,
    ClientNotStarted,
    MTProtoClientNotConnected,
    NoActiveGroupCall,
    NotInCallError,
)
from pytgcalls.types import (
    AudioQuality,
    GroupCallConfig,
    MediaStream,
    StreamEnded,
    VideoQuality,
)
from redis.exceptions import RedisError

from Emilia.application import pgram, redis_client
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command
from Emilia.database.chats_settings import (
    autoplay_db,
    get_autoplay_setting_cached,
    get_playmenu_setting_cached,
    playmenu_db,
)
from Emilia.locales import tr
from Emilia.modules.music.core.call import assistant, emilia_call
from Emilia.modules.music.core.youtube import (
    ensure_local_file,
    fetch_and_download,
    get_playlist_tracks,
    get_related_tracks,
    resolve_audio,
    search_youtube,
)
from Emilia.modules.music.playlist.core import session_finish
from Emilia.modules.music.utils.store import (
    add_many_to_queue,
    add_to_queue,
    clear_autoplay_queue,
    clear_menu,
    clear_queue,
    get_autoplay_queue,
    get_loop_mode,
    get_menu,
    get_now_playing,
    get_paused,
    get_playback_message_id,
    get_queue,
    get_shuffle_mode,
    pop_autoplay_next,
    pop_next,
    remove_from_queue,
    set_autoplay_queue,
    set_loop_mode,
    set_menu,
    set_now_playing,
    set_paused,
    set_playback_message_id,
    set_queue_direct,
    set_shuffle_mode,
    update_queue_track,
)
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.command_help import reply_usage
from Emilia.utils.command_policy import check_chat_scope
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.errors import report_error
from Emilia.utils.menu_guard import CallbackAccess, claim_tap
from Emilia.utils.message_actor import message_actor
from Emilia.utils.tasks import spawn

LOGGER = logging.getLogger(__name__)


THUMB = ""

# Membership lasts until someone kicks the assistant, which arrives as a chat
# update we listen for...the TTL is just a backstop for kicks we never saw.
_ASSISTANT_TTL = 3600
_ASSISTANT_FLOOD_KEY = f"{Config.CACHE_NAMESPACE}:music:{Config.BOT_ID}:assistant_link_flood"
_join_locks: dict[int, asyncio.Lock] = {}
_stream_end_state: dict[int, tuple[set, set]] = {}

_NEEDS_INVITE_RIGHTS = tr("music.need_admin_here_invite_users_via_link_permission")
_ASSISTANT_BANNED = tr("music.music_assistant_banned_from_group_unban_try_again")
_ACTIVE_STATUSES = {
    ChatMemberStatus.OWNER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.RESTRICTED,
}


def _assistant_key(chat_id) -> str:
    return f"{Config.CACHE_NAMESPACE}:music:{Config.BOT_ID}:assistant_in:{chat_id}"


async def forget_assistant_membership(chat_id) -> None:
    await redis_client.delete(_assistant_key(chat_id))


async def _assistant_me():
    me = getattr(assistant, "me", None)
    if not me:
        me = await assistant.get_me()
        assistant.me = me
    return me


async def _check_access(user_id, message, chat_id):
    now = await get_now_playing(chat_id)
    if now and now.get("user_id"):
        if user_id == now["user_id"]:
            return True
        if await is_user_admin(message, chat_id=chat_id, user_id=user_id, silent=True):
            return True
        return False
    return True


@dataclass(frozen=True)
class PlaybackAccess(CallbackAccess):
    target_chat_id: int | None = None
    require_player_message: bool = True
    allow_idle: bool = False

    async def resolve_chat(self, client, query):
        return self.target_chat_id or query.message.chat.id

    async def resolve_owner(self, client, query):
        chat_id = await self.resolve_chat(client, query)
        if self.require_player_message and query.message.id != await get_playback_message_id(
            chat_id
        ):
            return None
        now = await get_now_playing(chat_id)
        if not now and self.allow_idle:
            return query.from_user.id
        return (now.get("user_id") or 0) if now else None


_PLAYBACK_ACCESS = PlaybackAccess(
    allow_admin=True, denial="music.you_don_t_have_permission_to_control"
)


async def _check_command_access(message, chat_id):
    actor_id, _ = message_actor(message)
    return await _check_access(actor_id, message, chat_id)


async def _ensure_assistant_in_chat(chat_id: int) -> tuple[bool, str | None]:
    if await redis_client.get(_assistant_key(chat_id)):
        return True, None

    lock = _join_locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        if await redis_client.get(_assistant_key(chat_id)):
            return True, None
        ok, err = await _join_assistant(chat_id)
        if ok:
            await redis_client.setex(_assistant_key(chat_id), _ASSISTANT_TTL, "1")
        return ok, err


async def _join_assistant(chat_id: int) -> tuple[bool, str | None]:
    me = await _assistant_me()
    assistant_id = me.id
    username = getattr(me, "username", None)
    assistant_mention = f"@{username}" if username else (me.first_name or "assistant")

    # 1. Check if already an active member in the group
    try:
        member = await pgram.get_chat_member(chat_id, assistant_id)
        if member.status in _ACTIVE_STATUSES:
            return True, None
        if member.status == ChatMemberStatus.BANNED:
            try:
                await pgram.unban_chat_member(chat_id, assistant_id)
            except RPCError:
                return False, _ASSISTANT_BANNED.format(username=me.username or me.first_name)
    except UserNotParticipant:
        pass
    except FloodWait as e:
        await report_error(
            "music.assistant_get_member.flood_wait", e, chat_id=chat_id, wait_seconds=e.value
        )
    except RPCError:
        pass

    # 2. Try direct add (bot adds assistant)
    try:
        await pgram.add_chat_members(chat_id, assistant_id)
        return True, None
    except UserAlreadyParticipant:
        return True, None
    except UserBannedInChannel:
        try:
            await pgram.unban_chat_member(chat_id, assistant_id)
            await pgram.add_chat_members(chat_id, assistant_id)
            return True, None
        except UserAlreadyParticipant:
            return True, None
        except RPCError:
            return False, _ASSISTANT_BANNED.format(username=me.username or me.first_name)
    except FloodWait as e:
        await report_error(
            "music.assistant_add.flood_wait", e, chat_id=chat_id, wait_seconds=e.value
        )
    except RPCError as e:
        LOGGER.debug("[Music] Direct add failed for %s: %s", chat_id, e)

    # 3. Join via public username or invite link
    if await redis_client.get(_ASSISTANT_FLOOD_KEY):
        return False, (
            tr(
                "music.couldn_t_add_music_assistant_group_please_add",
                assistant_mention=assistant_mention,
            )
        )

    try:
        chat = await pgram.get_chat(chat_id)
        chat_username = getattr(chat, "username", None)
        if chat_username:
            try:
                await assistant.join_chat(chat_username)
                return True, None
            except UserAlreadyParticipant:
                return True, None
            except UserBannedInChannel:
                return False, _ASSISTANT_BANNED.format(username=me.username or me.first_name)
            except RPCError as e:
                LOGGER.debug("[Music] Join by chat username failed for %s: %s", chat_id, e)

        # Private chat or username join failed: create single-use invite link
        link = (
            await pgram.create_chat_invite_link(
                chat_id,
                name=tr("music.music_assistant"),
                member_limit=1,
                expire_date=datetime.now(UTC) + timedelta(minutes=15),
            )
        ).invite_link

        await assistant.join_chat(link)
        return True, None
    except UserAlreadyParticipant:
        return True, None
    except InviteRequestSent:
        return False, tr("music.admin_must_approve_assistant_s_join_request_then")
    except ChatAdminRequired:
        return False, _NEEDS_INVITE_RIGHTS
    except UserBannedInChannel:
        return False, _ASSISTANT_BANNED.format(username=me.username or me.first_name)
    except FloodWait as e:
        await redis_client.setex(_ASSISTANT_FLOOD_KEY, max(1, e.value), "1")
        await report_error(
            "music.assistant_link.flood_wait", e, chat_id=chat_id, wait_seconds=e.value
        )
        return False, (
            tr(
                "music.couldn_t_add_music_assistant_group_please_add",
                assistant_mention=assistant_mention,
            )
        )
    except UserChannelsTooMuch:
        return False, tr(
            "music.music_assistant_has_joined_too_many_chats_please",
            assistant_mention=assistant_mention,
        )
    except RPCError as e:
        LOGGER.warning("[Music] Assistant join via invite link failed for %s: %s", chat_id, e)

    return False, (
        tr(
            "music.could_not_add_music_assistant_add_directly_make",
            assistant_mention=assistant_mention,
        )
    )


async def _is_in_call(chat_id):
    try:
        participants = await emilia_call.get_participants(chat_id)
        return bool(participants)
    except (
        RPCError,
        OSError,
        BaseRTCException,
        ClientNotStarted,
        MTProtoClientNotConnected,
        NoActiveGroupCall,
    ):
        return False


async def _safe_edit_reply_markup(message, markup):
    try:
        await message.edit_reply_markup(markup)
    except RPCError as e:
        LOGGER.debug("[Music] Failed to edit reply markup: %s", e)


def _fmt_duration(seconds):
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "N/A"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _build_playback_markup(track_info: dict, chat_id: int = None):
    loop_mode = track_info.get("loop_mode", "off")
    shuffle = track_info.get("shuffle", False)

    loop_emoji = {"off": "🔁", "one": "🔂", "all": "🔁"}.get(loop_mode, "🔁")
    shuffle_text = "🔀 Shuffle" if not shuffle else tr("music.shuffle_build_playback_markup")

    rows = [
        [
            InlineKeyboardButton(
                tr("music.pause"),
                callback_data="music_pause",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                tr("music.resume"),
                callback_data="music_resume",
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                tr("music.loop_build_playback_markup", loop_emoji=loop_emoji),
                callback_data=f"music_loop:{loop_mode}",
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                shuffle_text, callback_data="music_shuffle", style=ButtonStyle.PRIMARY
            ),
            InlineKeyboardButton(
                tr("music.stop"), callback_data="music_stop", style=ButtonStyle.DANGER
            ),
        ],
    ]

    video_id = track_info.get("id") or ""
    if video_id:
        rows.append(
            [
                InlineKeyboardButton(
                    tr("music.save_to_liked"), callback_data=f"pl_like:{video_id}"
                ),
                InlineKeyboardButton(tr("music.playlists"), callback_data="pl:root::new"),
            ]
        )

    return InlineKeyboardMarkup(rows)


def _build_menu_markup(idx: int, total: int):
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("music.play"),
                    callback_data="music_choose",
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    tr("music.queue"),
                    callback_data="music_queue_add",
                    style=ButtonStyle.SUCCESS,
                ),
                InlineKeyboardButton(
                    tr("buttons.cancel"),
                    callback_data="music_cancel",
                    style=ButtonStyle.DANGER,
                ),
            ],
            [
                InlineKeyboardButton(
                    tr("music.prev"),
                    callback_data="music_prev",
                    style=ButtonStyle.DEFAULT,
                ),
                InlineKeyboardButton(
                    tr("music.build_menu_markup_idx_total", idx=idx + 1, total=total),
                    callback_data="music_ignore",
                    style=ButtonStyle.DEFAULT,
                ),
                InlineKeyboardButton(
                    tr("music.next"),
                    callback_data="music_next",
                    style=ButtonStyle.DEFAULT,
                ),
            ],
        ]
    )


def _build_caption(track_info, mention, prefix=tr("music.events.playing_now")):
    loop_mode = track_info.get("loop_mode", "off")
    shuffle = track_info.get("shuffle", False)
    extra = ""
    if loop_mode != "off":
        extra += f"\n`•` **Loop:** `{loop_mode}`"
    if shuffle:
        extra += tr("music.shuffle_build_caption")

    title = track_info["title"]
    url = track_info.get("webpage_url")
    track_display = f"[{title}]({url})" if url else title
    user_label = tr("music.autoplay_youtube_mix") if mention == "Autoplay" else mention

    return tr(
        "music.track_duration_user",
        prefix=prefix.strip("*"),
        track_display=track_display,
        duration=_fmt_duration(track_info.get("duration")),
        user_label=user_label,
        extra=extra,
    )


def _menu_text(cand, idx, total):
    return tr(
        "music.pick_track_track_channel_duration_use_browse_then",
        idx=idx + 1,
        total=total,
        title=cand["title"],
        uploader=cand.get("uploader", "Unknown"),
        duration=_fmt_duration(cand.get("duration")),
    )


def _make_stream(track_info):
    path = track_info.get("file_path", "")
    title = track_info.get("title", "Unknown")
    if not path:
        raise FileNotFoundError(f"no local file for {title!r}")
    LOGGER.debug("[Music] Creating stream for '%s' from '%s'", title, path)
    if track_info.get("is_video"):
        return MediaStream(
            path,
            audio_parameters=AudioQuality.HIGH,
            video_parameters=VideoQuality.HD_720p,
        )

    return MediaStream(
        path,
        audio_parameters=AudioQuality.HIGH,
        video_flags=MediaStream.Flags.IGNORE,
    )


def _stream_end_ready(chat_id, stream_type):
    state = _stream_end_state.get(chat_id)
    if not state:
        return False
    expected, ended = state
    if stream_type not in expected:
        return False
    ended.add(stream_type)
    if ended != expected:
        return False
    _stream_end_state.pop(chat_id, None)
    return True


def _clear_stream_end_state(chat_id):
    _stream_end_state.pop(chat_id, None)


async def _safe_play(chat_id, stream):
    config = GroupCallConfig(auto_start=True)
    _clear_stream_end_state(chat_id)
    try:
        await emilia_call.play(chat_id, stream, config=config)
    except (ConnectionNotFound, NotInCallError):
        LOGGER.info("[Music] Re-joining voice call for chat %s before playing", chat_id)
        try:
            await emilia_call.leave_call(chat_id)
        except NotInCallError:
            pass
        await emilia_call.play(chat_id, stream, config=config)
    except (ChannelPrivate, UserNotParticipant):
        LOGGER.info(
            "[Music] Assistant not joined in %s during play; re-joining and retrying", chat_id
        )
        await forget_assistant_membership(chat_id)
        ok, _ = await _ensure_assistant_in_chat(chat_id)
        if not ok:
            raise
        await emilia_call.play(chat_id, stream, config=config)
    expected = set()
    if stream.microphone is not None:
        expected.add(StreamEnded.Type.AUDIO)
    if stream.camera is not None:
        expected.add(StreamEnded.Type.VIDEO)
    _stream_end_state[chat_id] = (expected, set())


async def _edit_sent(sent, text: str):
    if sent.caption is not None:
        await sent.edit_caption(text)
    else:
        await sent.edit_text(text)


async def _delete_old_playback_message(chat_id):
    old_msg_id = await get_playback_message_id(chat_id)
    if old_msg_id:
        try:
            await pgram.delete_messages(chat_id, old_msg_id)
        except RPCError:
            pass
        await set_playback_message_id(chat_id, None)


_prefetch_tasks: dict[int, asyncio.Task] = {}


def _clear_prefetch_task(chat_id, task):
    if _prefetch_tasks.get(chat_id) is task:
        _prefetch_tasks.pop(chat_id, None)


async def _prefetch_and_update(chat_id, track_key, url, is_video):
    try:
        track_info = await fetch_and_download(url, is_video)
        q = await get_queue(chat_id)
        track_id = track_info.get("id")
        updated_q = False
        for queued in q:
            queued_key = queued.get("id") or queued.get("webpage_url")
            if queued_key == track_id or queued_key == track_key:
                await update_queue_track(
                    chat_id, queued["_queue_id"], file_path=track_info["file_path"]
                )
                updated_q = True
                break
        if not updated_q:
            auto_q = await get_autoplay_queue(chat_id)
            for queued in auto_q:
                queued_key = queued.get("id") or queued.get("webpage_url")
                if queued_key == track_id or queued_key == track_key:
                    await update_queue_track(
                        chat_id,
                        queued["_queue_id"],
                        autoplay=True,
                        file_path=track_info["file_path"],
                    )
                    break
    except Exception as exc:
        LOGGER.debug("[Music] Prefetch failed for %s: %s", track_key, exc)


async def prefetch_next(chat_id):
    q = await get_queue(chat_id)
    track = None
    if q:
        track = q[0]
    else:
        if await get_autoplay_setting_cached(chat_id):
            auto_q = await get_autoplay_queue(chat_id)
            if not auto_q:
                now = await get_now_playing(chat_id)
                if now and now.get("id"):
                    try:
                        related = await get_related_tracks(now["id"], limit=25)
                        if related:
                            await set_autoplay_queue(chat_id, related)
                            auto_q = related
                    except RedisError:
                        LOGGER.debug("Could not prefetch related tracks", exc_info=True)
            if auto_q:
                track = auto_q[0]

    if not track:
        return

    path = track.get("file_path")
    if path and os.path.exists(path) and os.path.getsize(path) > 1024:
        return
    url = track.get("webpage_url", "")
    if not url.startswith("http"):
        return
    track_key = track.get("id") or url
    existing = _prefetch_tasks.get(chat_id)
    if existing and not existing.done():
        return
    task = spawn(
        _prefetch_and_update(chat_id, track_key, url, track.get("is_video", False)),
        name=f"prefetch:{chat_id}:{track_key}",
    )
    _prefetch_tasks[chat_id] = task
    task.add_done_callback(lambda done, key=chat_id: _clear_prefetch_task(key, done))


async def _start_playback(
    chat_id, track_info, mention, menu_message=None, reply_message=None, user_id=None
):
    now = await get_now_playing(chat_id)
    in_call = await _is_in_call(chat_id)
    is_playing = (
        in_call and now and now.get("file_path") and os.path.exists(now.get("file_path", ""))
    )

    if is_playing:
        existing = await get_queue(chat_id)
        now_url = now.get("webpage_url") if now else None
        track_url = track_info.get("webpage_url")
        if now_url == track_url or any(t.get("webpage_url") == track_url for t in existing):
            target = menu_message or reply_message
            if menu_message:
                await menu_message.delete()
            await target.reply_text(
                text=tr("music.this_track_is_already_in_the_queue"),
                reply_markup=_build_playback_markup(track_info, chat_id),
            )
            return

        if user_id is not None:
            track_info["user_id"] = user_id
        if mention:
            track_info["requester_mention"] = mention
        pos = await add_to_queue(chat_id, track_info)
        if menu_message:
            try:
                await menu_message.delete()
            except RPCError:
                pass
        photo = track_info.get("thumbnail", THUMB)
        cap = _build_caption(track_info, mention, tr("music.added_queue_start_playback", pos=pos))
        markup = _build_playback_markup(track_info, chat_id)
        if reply_message is not None:
            try:
                sent = await reply_message.reply_photo(
                    photo=photo, caption=cap, reply_markup=markup
                )
            except RPCError:
                sent = await reply_message.reply_text(text=cap, reply_markup=markup)
        else:
            try:
                sent = await pgram.send_photo(
                    chat_id, photo=photo, caption=cap, reply_markup=markup
                )
            except RPCError:
                sent = await pgram.send_message(chat_id, text=cap, reply_markup=markup)
        await set_playback_message_id(chat_id, sent.id)
        spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
        return

    if user_id is not None:
        track_info["user_id"] = user_id
    if mention:
        track_info["requester_mention"] = mention
    cap = _build_caption(track_info, mention)
    markup = _build_playback_markup(track_info, chat_id)
    thumb = track_info.get("thumbnail", THUMB)

    await _delete_old_playback_message(chat_id)
    if menu_message:
        try:
            await menu_message.delete()
        except RPCError:
            pass
    if reply_message is not None:
        try:
            sent = await reply_message.reply_photo(photo=thumb, caption=cap, reply_markup=markup)
        except RPCError:
            sent = await reply_message.reply_text(text=cap, reply_markup=markup)
    else:
        try:
            sent = await pgram.send_photo(chat_id, photo=thumb, caption=cap, reply_markup=markup)
        except RPCError:
            sent = await pgram.send_message(chat_id, text=cap, reply_markup=markup)

    ok, err = await _ensure_assistant_in_chat(chat_id)
    if not ok:
        await _edit_sent(sent, err)
        return

    try:
        await _safe_play(chat_id, _make_stream(track_info))
    except (ChannelPrivate, UserNotParticipant):
        await _edit_sent(sent, tr("music.please_add_music_assistant_group_can_join_voice"))
        return
    except FloodWait as e:
        await report_error(
            "music.play.flood_wait",
            e,
            chat_id=chat_id,
            track=track_info.get("title"),
            wait_seconds=e.value,
        )
        await _edit_sent(sent, tr("music.couldn_t_start_stream_right_now_please_try"))
        return
    except NoActiveGroupCall:
        await sent.edit_caption(tr("music.i_couldn_t_find_or_start_the"))
        return
    except (ConnectionNotFound, GroupCallInvalid, GroupcallForbidden):
        await sent.edit_caption(tr("music.voice_chat_is_unavailable_start_it_manually"))
        return
    except ChatAdminRequired:
        await sent.edit_caption(tr("music.i_couldn_t_start_or_join_the"))
        return
    except PeerIdInvalid:
        await sent.edit_caption(tr("music.unable_to_resolve_this_chat_try_sending"))
        return
    except CallBusy:
        await sent.edit_caption(tr("music.the_voice_chat_is_currently_busy_or"))
        return
    except ClientNotStarted:
        await sent.edit_caption(tr("music.the_assistant_client_is_offline_please_report"))
        return
    except Exception as e:
        await report_error("music.play", e, chat_id=chat_id, track=track_info.get("title"))
        await sent.edit_caption(tr("music.i_couldn_t_start_the_stream_the"))
        return

    await set_paused(chat_id, False)
    await set_now_playing(chat_id, track_info)
    await set_playback_message_id(chat_id, sent.id)
    spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")


async def _show_menu(message: Message, query: str, is_video: bool):
    msg = await message.reply_text(tr("music.searching"))
    candidates = await search_youtube(query, limit=8)
    if not candidates:
        return await msg.edit_text(tr("findanime.no_results_found"))
    # The anonymous-admin confirmation supplies the real menu owner.
    actor_id, _ = message_actor(message)
    await msg.delete()
    cand = candidates[0]
    try:
        sent = await message.reply_photo(
            photo=cand.get("thumbnail") or THUMB,
            caption=_menu_text(cand, 0, len(candidates)),
            reply_markup=_build_menu_markup(0, len(candidates)),
        )
    except RPCError:
        sent = await message.reply_text(
            _menu_text(cand, 0, len(candidates)),
            reply_markup=_build_menu_markup(0, len(candidates)),
        )
    await set_menu(
        message.chat.id,
        {
            "candidates": candidates,
            "index": 0,
            "user_id": actor_id,
            "is_video": is_video,
            "query": query,
            "message_id": sent.id,
        },
    )


class _MusicMenuAccess(CallbackAccess):
    async def resolve_owner(self, client, query):
        menu = await get_menu(query.message.chat.id)
        if not menu or query.message.id != menu.get("message_id"):
            return None
        query._emilia_music_menu = menu
        return menu.get("user_id")


_MUSIC_MENU_ACCESS = _MusicMenuAccess(denial="music.this_isn_t_your_menu")


async def _navigate(query, delta):
    menu = query._emilia_music_menu
    cands = menu["candidates"]
    i = (menu["index"] + delta) % len(cands)
    menu["index"] = i
    await set_menu(query.message.chat.id, menu)
    cand = cands[i]
    try:
        await query.message.edit_media(
            InputMediaPhoto(
                cand.get("thumbnail") or THUMB, caption=_menu_text(cand, i, len(cands))
            ),
            reply_markup=_build_menu_markup(i, len(cands)),
        )
    except RPCError:
        try:
            await query.message.edit_caption(
                _menu_text(cand, i, len(cands)),
                reply_markup=_build_menu_markup(i, len(cands)),
            )
        except RPCError:
            pass
    await query.answer()


async def _check_if_clone(client, target):
    if not await check_chat_scope(target, "group"):
        return True

    if getattr(client, "is_clone", False) or (
        getattr(client, "me", None) and client.me.id != Config.BOT_ID
    ):
        text = tr(
            "music.music_system_disabled_clones_prevent_server_overloads_youtube",
            bot_username=Config.BOT_USERNAME,
            bot_username_2=Config.BOT_USERNAME,
            bot_username_3=Config.BOT_USERNAME,
        )
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        tr("music.add", bot_username=Config.BOT_USERNAME),
                        url=f"https://t.me/{Config.BOT_USERNAME}?startgroup=true",
                    )
                ]
            ]
        )
        if isinstance(target, CallbackQuery):
            try:
                await target.answer(
                    tr("music.music_system_is_disabled_on_cloned_bots"),
                    show_alert=True,
                )
            except RPCError:
                pass
            try:
                if target.message:
                    await target.message.reply_text(
                        text,
                        reply_markup=markup,
                        link_preview_options=LinkPreviewOptions(is_disabled=True),
                    )
            except RPCError:
                pass
        else:
            try:
                await target.reply_text(
                    text,
                    reply_markup=markup,
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
            except RPCError:
                pass
        return True
    return False


@callbackquery(pattern=r"^music_ignore$", access=CallbackAccess(public=True))
async def menu_ignore_cb(client, query):
    if await _check_if_clone(client, query):
        return
    await query.answer()


@callbackquery(pattern=r"^music_prev$", access=_MUSIC_MENU_ACCESS)
async def menu_prev_cb(client, query):
    if await _check_if_clone(client, query):
        return
    await _navigate(query, -1)


@callbackquery(pattern=r"^music_next$", access=_MUSIC_MENU_ACCESS)
async def menu_next_cb(client, query):
    if await _check_if_clone(client, query):
        return
    await _navigate(query, 1)


@callbackquery(pattern=r"^music_cancel$", access=_MUSIC_MENU_ACCESS)
async def menu_cancel_cb(client, query):
    if await _check_if_clone(client, query):
        return
    await clear_menu(query.message.chat.id)
    await query.message.delete()
    await query.answer(tr("clone.cancelled"))


@callbackquery(pattern=r"^music_choose$", access=_MUSIC_MENU_ACCESS)
async def menu_choose_cb(client, query):
    if await _check_if_clone(client, query):
        return
    menu = query._emilia_music_menu
    # Resolving audio is slow, so the card sits there inviting a second tap
    if not await claim_tap(
        query.from_user.id, f"music_choose:{query.message.id}", ttl=30, client=client
    ):
        return await query.answer(tr("music.already_loading_that"))
    await query.answer()
    cand = menu["candidates"][menu["index"]]
    try:
        await query.message.delete()
        track_info = await resolve_audio(cand, menu["is_video"])
    except ValueError as ve:
        return await query.message.reply_text(tr("admin.dare_dare", dare=ve))
    except Exception as e:
        LOGGER.error("Failed to resolve audio: %s", e, exc_info=True)
        return await query.message.reply_text(tr("music.failed_to_download_track_try_again"))

    await _start_playback(
        query.message.chat.id,
        track_info,
        query.from_user.mention,
        menu_message=query.message,
        user_id=query.from_user.id,
    )


@callbackquery(pattern=r"^music_queue_add$", access=_MUSIC_MENU_ACCESS)
async def menu_queue_add_cb(client, query):
    if await _check_if_clone(client, query):
        return
    menu = query._emilia_music_menu
    if not await claim_tap(
        query.from_user.id, f"music_queue_add:{query.message.id}", client=client
    ):
        return await query.answer(tr("music.already_adding_that"))
    cand = menu["candidates"][menu["index"]]
    chat_id = query.message.chat.id

    # Duplicate detection
    existing = await get_queue(chat_id)
    if any(t.get("webpage_url") == cand.get("webpage_url") for t in existing):
        return await query.answer(tr("music.this_track_is_already_in_the_queue"), show_alert=True)

    cand["user_id"] = query.from_user.id
    cand["requester_mention"] = query.from_user.mention
    await add_to_queue(chat_id, cand)
    # Start fetching it now rather than when the current track ends, so the
    # handover between songs has no silent gap.
    spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
    await query.answer(tr("music.added_queue", title=cand["title"]), show_alert=False)


async def _do_pause(chat_id):
    now = await get_now_playing(chat_id)
    if not now:
        return False, tr("music.nothing_playing")
    if await get_paused(chat_id):
        return False, tr("music.playback_already_paused")
    try:
        await emilia_call.pause(chat_id)
        await set_paused(chat_id, True)
        return True, None
    except (
        RPCError,
        RedisError,
        OSError,
        BaseRTCException,
        NotInCallError,
        ClientNotStarted,
        MTProtoClientNotConnected,
    ) as e:
        LOGGER.error("[Music] Failed to pause chat %s: %s", chat_id, e)
        return False, tr("music.could_not_pause_playback")


async def _do_resume(chat_id):
    now = await get_now_playing(chat_id)
    if not now:
        return False, tr("music.nothing_playing")
    if not await get_paused(chat_id):
        return False, tr("music.playback_already_active_not_paused")
    try:
        await emilia_call.resume(chat_id)
        await set_paused(chat_id, False)
        return True, None
    except (
        RPCError,
        RedisError,
        OSError,
        BaseRTCException,
        NotInCallError,
        ClientNotStarted,
        MTProtoClientNotConnected,
    ) as e:
        LOGGER.error("[Music] Failed to resume chat %s: %s", chat_id, e)
        return False, tr("music.could_not_resume_playback")


async def _do_stop(chat_id):
    now = await get_now_playing(chat_id)
    in_call = await _is_in_call(chat_id)
    q = await get_queue(chat_id)
    if not now and not in_call and not q:
        return False, tr("music.nothing_stop")
    try:
        await emilia_call.leave_call(chat_id)
    except (
        RPCError,
        OSError,
        BaseRTCException,
        NotInCallError,
        NoActiveGroupCall,
        ClientNotStarted,
        MTProtoClientNotConnected,
    ):
        pass
    _clear_stream_end_state(chat_id)
    await clear_queue(chat_id)
    await set_now_playing(chat_id, None)
    await set_paused(chat_id, False)
    await set_loop_mode(chat_id, "off")
    await set_shuffle_mode(chat_id, False)
    await _delete_old_playback_message(chat_id)
    await session_finish(chat_id)
    return True, None


@callbackquery(pattern=r"^music_pause$", access=_PLAYBACK_ACCESS)
async def pause_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    ok, err = await _do_pause(chat_id)
    await query.answer(tr("music.playback_paused") if ok else err, show_alert=not ok)


@callbackquery(pattern=r"^music_resume$", access=_PLAYBACK_ACCESS)
async def resume_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    ok, err = await _do_resume(chat_id)
    await query.answer(tr("music.playback_resumed") if ok else err, show_alert=not ok)


async def _handle_skip(chat_id):
    now = await get_now_playing(chat_id)
    loop_mode = await get_loop_mode(chat_id)
    shuffle = await get_shuffle_mode(chat_id)

    if not now:
        return None, tr("music.nothing_playing")

    requester_mention = now.get("requester_mention") or "User"
    skipped_past_loop_one = loop_mode == "one"

    nxt = await pop_next(chat_id)
    if not nxt and loop_mode == "all":
        await _do_stop(chat_id)
        return {
            "caption": (tr("music.skipped_track_last_one_loop_all_had_nothing")),
            "photo": None,
            "reply_markup": None,
        }, None
    if nxt:
        await clear_autoplay_queue(chat_id)
    else:
        if await get_autoplay_setting_cached(chat_id):
            try:
                nxt = await pop_autoplay_next(chat_id)
                if not nxt and now:
                    seed_id = now.get("id")
                    if not seed_id and now.get("title"):
                        search_res = await search_youtube(now["title"], limit=1)
                        if search_res:
                            seed_id = search_res[0].get("id")
                    if seed_id:
                        related = await get_related_tracks(seed_id, limit=25)
                        if related:
                            nxt = related[0]
                            if len(related) > 1:
                                await set_autoplay_queue(chat_id, related[1:])

                if nxt:
                    nxt["requester_mention"] = "Autoplay"
                    nxt.setdefault("loop_mode", now.get("loop_mode", "off"))
                    nxt.setdefault("shuffle", now.get("shuffle", False))
            except RedisError as e:
                LOGGER.warning("[Music] Skip autoplay fetch failed for %s: %s", chat_id, e)
        if not nxt:
            await _do_stop(chat_id)
            tail = tr("music.loop_one_still_turn_off_loop_off") if skipped_past_loop_one else ""
            return {
                "caption": tr("music.skipped_track_queue_empty_playback_stopped") + tail,
                "photo": None,
                "reply_markup": None,
            }, None

    # Handle shuffle
    if shuffle:
        remaining = await get_queue(chat_id)
        if len(remaining) > 1:
            random.shuffle(remaining)
            await set_queue_direct(chat_id, remaining)

    nxt_mention = nxt.get("requester_mention") or requester_mention
    nxt.setdefault("loop_mode", now.get("loop_mode", "off"))
    nxt.setdefault("shuffle", now.get("shuffle", False))
    await set_now_playing(chat_id, nxt)

    await set_paused(chat_id, False)

    try:
        nxt = await ensure_local_file(nxt)
        await _safe_play(chat_id, _make_stream(nxt))
        spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
    except NoActiveGroupCall:
        await set_now_playing(chat_id, None)
        return None, tr("music.i_couldn_t_find_or_start_the")
    except (ConnectionNotFound, GroupCallInvalid, GroupcallForbidden):
        await set_now_playing(chat_id, None)
        return None, tr("music.voice_chat_is_unavailable_start_it_manually")
    except (ChannelPrivate, UserNotParticipant):
        await set_now_playing(chat_id, None)
        return None, tr("music.music_assistant_not_group_please_add_invite_assistant")
    except FloodWait as e:
        await set_now_playing(chat_id, None)
        await report_error(
            "music.skip.flood_wait",
            e,
            chat_id=chat_id,
            track=nxt.get("title"),
            wait_seconds=e.value,
        )
        return None, tr("music.couldn_t_play_next_track_right_now_please")
    except ValueError as e:
        await set_now_playing(chat_id, None)
        LOGGER.warning("[Music] Could not fetch %s for %s: %s", nxt.get("title"), chat_id, e)
        return None, tr("music.couldn_t_download_skip_again_move", title=nxt.get("title"))
    except Exception as e:
        await set_now_playing(chat_id, None)
        await report_error("music.skip", e, chat_id=chat_id, track=nxt.get("title"))
        return None, tr("music.couldn_t_play_next_track_developers_have_notified")

    caption = _build_caption(nxt, nxt_mention, tr("music.track_skipped"))
    if skipped_past_loop_one:
        caption += tr("music.loop_one_still_loop_off_stop_repeating")

    return {
        "photo": nxt.get("thumbnail") or THUMB,
        "caption": caption,
        "reply_markup": _build_playback_markup(nxt, chat_id),
    }, None


@callbackquery(pattern=r"^music_skip$", access=_PLAYBACK_ACCESS)
async def skip_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    if not await claim_tap(chat_id, "music_skip", client=client):
        return await query.answer(tr("music.already_skipping"))
    msg_dict, err = await _handle_skip(chat_id)
    if err:
        await query.answer(err, show_alert=True)
    elif msg_dict:
        await _delete_old_playback_message(chat_id)
        await query.message.delete()
        if msg_dict.get("photo") is None:
            sent = await query.message.reply_text(
                msg_dict.get("caption", ""), reply_markup=msg_dict.get("reply_markup")
            )
        else:
            try:
                sent = await query.message.reply_photo(**msg_dict)
            except RPCError:
                sent = await query.message.reply_text(
                    msg_dict.get("caption", ""), reply_markup=msg_dict.get("reply_markup")
                )
        await set_playback_message_id(chat_id, sent.id)


@callbackquery(pattern=r"^music_stop$", access=_PLAYBACK_ACCESS)
async def stop_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    if not await claim_tap(chat_id, "music_stop", client=client):
        return await query.answer(tr("music.already_stopping"))
    ok, err = await _do_stop(chat_id)
    if not ok:
        return await query.answer(err, show_alert=True)
    await _delete_old_playback_message(chat_id)
    await query.message.delete()
    await query.message.reply_text(tr("music.playback_ended_and_queue_cleared"))


@callbackquery(pattern=r"^music_loop:", access=_PLAYBACK_ACCESS)
async def loop_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    modes = ["off", "one", "all"]
    current = await get_loop_mode(chat_id)
    next_mode = modes[(modes.index(current) + 1) % len(modes)] if current in modes else "off"
    await set_loop_mode(chat_id, next_mode)

    now = await get_now_playing(chat_id)
    if now:
        now["loop_mode"] = next_mode
        await set_now_playing(chat_id, now)
        await _safe_edit_reply_markup(query.message, _build_playback_markup(now, chat_id))
    await query.answer(tr("music.loop", next_mode=next_mode), show_alert=False)


@callbackquery(pattern=r"^music_shuffle$", access=_PLAYBACK_ACCESS)
async def shuffle_cb(client, query):
    if await _check_if_clone(client, query):
        return
    chat_id = query.message.chat.id
    current = await get_shuffle_mode(chat_id)
    new = not current
    await set_shuffle_mode(chat_id, new)

    now = await get_now_playing(chat_id)
    if now:
        now["shuffle"] = new
        await set_now_playing(chat_id, now)
        await _safe_edit_reply_markup(query.message, _build_playback_markup(now, chat_id))
    await query.answer(tr("music.shuffle", enabled="on" if new else "off"), show_alert=False)


@command(pattern="play|vplay", chat_scope="group")
@anonadmin_checker(named=True)
async def play_command(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    text = message.text or message.caption
    if not text:
        return

    spawn(_ensure_assistant_in_chat(message.chat.id), name=f"assistant_join:{message.chat.id}")

    parts = text.split()
    command = parts[0].lower()
    is_video = "vplay" in command

    track_info = None

    if len(parts) < 2:
        if message.reply_to_message:
            media = (
                getattr(message.reply_to_message, "audio", None)
                or getattr(message.reply_to_message, "voice", None)
                or getattr(message.reply_to_message, "video", None)
            )
            if media:
                from Emilia.modules.music.core.media import download_telegram_media

                track_id = f"telegram_{message.chat.id}_{message.reply_to_message.id}"
                extension = "mp4" if message.reply_to_message.video else "m4a"
                safe_name = os.path.join(Config.TEMP_DOWNLOAD_DIRECTORY, f"{track_id}.{extension}")
                try:
                    file_path = await download_telegram_media(
                        client, message.reply_to_message, safe_name
                    )
                except (RPCError, OSError, ValueError) as e:
                    LOGGER.error("Failed to download media: %s", e, exc_info=True)
                    return await message.reply_text(
                        tr("music.failed_to_download_media_please_try_again")
                    )
                if not file_path:
                    return await message.reply_text(tr("music.failed_to_download_media"))
                title = (
                    getattr(media, "title", None)
                    or getattr(media, "file_name", None)
                    or tr("music.telegram_media")
                )
                track_info = {
                    "id": track_id,
                    "source": "telegram",
                    "title": title,
                    "duration": getattr(media, "duration", 0),
                    "uploader": (
                        message.reply_to_message.from_user.first_name
                        if message.reply_to_message.from_user
                        else "Unknown"
                    ),
                    "thumbnail": THUMB,
                    "webpage_url": message.reply_to_message.link or "https://t.me",
                    "is_video": bool(message.reply_to_message.video),
                    "file_path": file_path,
                }
            elif message.reply_to_message.text:
                query = message.reply_to_message.text
            else:
                return await reply_usage(message)
        else:
            return await reply_usage(message)
    else:
        query = text.split(None, 1)[1]

    chat_id = message.chat.id
    user_id, mention = message_actor(message)

    if track_info:
        track_info["user_id"] = user_id
        await _start_playback(chat_id, track_info, mention, reply_message=message, user_id=user_id)
        return

    # Detect playlist URLs
    if "list=" in query:
        await message.reply_text(tr("music.loading_playlist"))
        try:
            pl_id = re.search(r"[?&]list=([^&]+)", query)
            if pl_id:
                tracks = await get_playlist_tracks(pl_id.group(1), limit=100)
                if not tracks:
                    return await message.reply_text(tr("music.playlist_is_empty_or_unavailable"))
                now = await get_now_playing(chat_id)
                in_call = await _is_in_call(chat_id)
                is_playing = (
                    in_call
                    and now
                    and now.get("file_path")
                    and os.path.exists(now.get("file_path", ""))
                )

                limit_note = (
                    tr("music.limited_100_tracks_per_request_stability")
                    if len(tracks) == 100
                    else ""
                )
                if is_playing:
                    await add_many_to_queue(chat_id, tracks)
                    await message.reply_text(
                        tr(
                            "music.added_tracks_from_playlist_queue_play_command",
                            tracks=len(tracks),
                            limit_note=limit_note,
                        )
                    )
                    spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
                    return
                else:
                    first = tracks[0]
                    remaining = tracks[1:]
                    if remaining:
                        await add_many_to_queue(chat_id, remaining)
                    await message.reply_text(
                        tr(
                            "music.playing_first_track_added_tracks_from_playlist_queue",
                            remaining=len(remaining),
                            limit_note=limit_note,
                        )
                    )
                    resolved = await fetch_and_download(first["webpage_url"], is_video)
                    if resolved:
                        first["file_path"] = (
                            resolved["file_path"] if isinstance(resolved, dict) else resolved
                        )
                        first["user_id"] = user_id
                        await _start_playback(
                            chat_id, first, mention, reply_message=message, user_id=user_id
                        )
                    return
        except Exception as e:
            LOGGER.error("Playlist load failed: %s", e, exc_info=True)
            return await message.reply_text(tr("music.playlist_load_failed_try_again"))

    playmenu = await get_playmenu_setting_cached(chat_id)
    if playmenu:
        await _show_menu(message, query, is_video)
    else:
        try:
            track_info = await fetch_and_download(query, is_video)
        except ValueError:
            return await message.reply_text(tr("findanime.no_results_found"))
        except Exception as e:
            await report_error("music.play_command", e, chat_id=chat_id, query=query)
            return await message.reply_text(tr("music.i_couldn_t_load_that_track_please"))

        await _start_playback(chat_id, track_info, mention, reply_message=message, user_id=user_id)


@command("now", chat_scope="group")
async def now_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    chat_id = message.chat.id
    now = await get_now_playing(chat_id)
    if not now:
        return await message.reply_text(tr("music.nothing_is_playing_right_now"))
    await _delete_old_playback_message(chat_id)
    _, mention = message_actor(message)
    try:
        sent = await message.reply_photo(
            photo=now.get("thumbnail", THUMB),
            caption=_build_caption(now, mention, tr("music.now_playing")),
            reply_markup=_build_playback_markup(now, chat_id),
        )
    except RPCError:
        sent = await message.reply_text(
            text=_build_caption(now, mention, tr("music.now_playing")),
            reply_markup=_build_playback_markup(now, chat_id),
        )
    await set_playback_message_id(chat_id, sent.id)


@command("queue", chat_scope="group")
async def queue_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    chat_id = message.chat.id
    q = await get_queue(chat_id)
    if not q:
        if await get_autoplay_setting_cached(chat_id) and await get_now_playing(chat_id):
            return await message.reply_text(tr("music.the_queue_is_empty_autoplay_will_continue"))
        return await message.reply_text(tr("music.the_queue_is_currently_empty"))

    lines = []
    for i, track in enumerate(q, start=1):
        title = html.escape(str(track.get("title") or "Unknown"), quote=False)
        title = title.replace("\r", " ").replace("\n", " ")
        raw_url = str(track.get("webpage_url") or "")
        url = html.escape(raw_url, quote=True)
        dur = html.escape(_fmt_duration(track.get("duration")), quote=False)
        display_title = f'<a href="{url}">{title}</a>' if raw_url.startswith("http") else title
        lines.append(
            tr(
                "music.queue_cmd_position_title_duration",
                position=i,
                title=display_title,
                duration=dur,
            )
        )
    text = tr("music.queue_queue_cmd") + "\n".join(lines) + "</blockquote>"

    await message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@command("remove", chat_scope="group")
async def remove_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2:
        return await reply_usage(message)
    try:
        pos = int(args[1])
    except ValueError:
        return await message.reply_text(tr("music.position_must_be_a_number"))
    chat_id = message.chat.id
    q = await get_queue(chat_id)
    if pos < 1 or pos > len(q):
        return await message.reply_text(
            tr("music.invalid_position_queue_has_tracks", invalid_position_queue=len(q))
        )
    removed = await remove_from_queue(chat_id, q[pos - 1]["_queue_id"])
    if removed is None:
        return await message.reply_text(tr("music.queue_changed_retry"))
    await message.reply_text(tr("music.removed_from_queue", title=removed["title"]))


@command("clearqueue", chat_scope="group")
async def clear_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    await clear_queue(message.chat.id)
    await message.reply_text(tr("music.queue_cleared"))


@command("loop", chat_scope="group")
async def loop_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1].lower() not in ["off", "one", "all"]:
        return await reply_usage(message)
    mode = args[1].lower()
    chat_id = message.chat.id
    await set_loop_mode(chat_id, mode)
    now = await get_now_playing(chat_id)
    if now:
        now["loop_mode"] = mode
        await set_now_playing(chat_id, now)
    await message.reply_text(tr("music.loop_mode_set", mode=mode))


@command("shuffle", chat_scope="group")
async def shuffle_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    args = message.text.split()
    if len(args) < 2 or args[1].lower() not in ["on", "off"]:
        return await reply_usage(message)
    mode = args[1].lower() == "on"
    chat_id = message.chat.id
    await set_shuffle_mode(chat_id, mode)
    now = await get_now_playing(chat_id)
    if now:
        now["shuffle"] = mode
        await set_now_playing(chat_id, now)
    await message.reply_text(tr("music.shuffle_set", enabled="on" if mode else "off"))


@command("playmenu", chat_scope="group")
@anonadmin_checker
async def playmenu_cmd(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    actor_id, _ = message_actor(message)
    if not await is_user_admin(message, user_id=actor_id):
        return

    parts = message.text.split()
    if len(parts) < 2:
        current = await get_playmenu_setting_cached(message.chat.id)
        state = "Enabled" if current else "Disabled"
        return await message.reply_text(
            tr("music.music_menu_currently_use_playmenu_playmenu_off", state=state)
        )

    arg = parts[1].lower()
    if arg in ["on", "true", "enable"]:
        await playmenu_db(message.chat.id, True)
        await message.reply_text(tr("music.play_menu_enabled_users_will_now_select"))
    elif arg in ["off", "false", "disable"]:
        await playmenu_db(message.chat.id, False)
        await message.reply_text(tr("music.play_menu_disabled_the_bot_will_now"))
    else:
        await message.reply_text(tr("music.invalid_argument_use_on_or_off"))


async def playlist_cmd(client: Client, message: Message):
    from Emilia.modules.music.playlist import import_engine as imports

    text = message.text or message.caption
    parts = text.split()
    if len(parts) < 2:
        return await message.reply_text(
            tr("music.usage_playlist_youtube_or_spotify_link_send"),
        )

    target = parts[1]
    kind, _ = imports.detect_source(target)
    if not kind:
        match = re.search(r"[?&]list=([^&]+)", target)
        pl_id = match.group(1) if match else target
        msg = await message.reply_text(tr("music.loading_playlist"))
        tracks = await get_playlist_tracks(pl_id, limit=30)
    else:
        msg = await message.reply_text(tr("music.loading", kind=imports.source_label(kind)))
        reporter = imports.ProgressReporter(msg, label="Loading")
        tracks, error = await imports.import_tracks(target, progress=reporter.update)
        await reporter.flush()
        if error:
            return await msg.edit_text(error)

    if not tracks:
        return await msg.edit_text(tr("music.playlist_is_empty_or_unavailable"))

    if not await get_now_playing(message.chat.id):
        first, rest = tracks[0], tracks[1:]
        if rest:
            await add_many_to_queue(message.chat.id, rest)
        await msg.edit_text(tr("music.added_tracks_from_playlist_queue", tracks=len(tracks)))
        try:
            first = await fetch_and_download(first["webpage_url"], False)
        except Exception as e:
            await report_error("music.playlist_cmd", e, chat_id=message.chat.id)
            return await msg.edit_text(tr("music.i_couldn_t_start_the_first_track"))
        user_id, mention = message_actor(message)
        first["user_id"] = user_id
        await _start_playback(
            message.chat.id, first, mention, reply_message=message, user_id=user_id
        )
    else:
        await add_many_to_queue(message.chat.id, tracks)
        await msg.edit_text(tr("music.added_tracks_from_playlist_queue", tracks=len(tracks)))
        spawn(prefetch_next(message.chat.id), name=f"prefetch_next:{message.chat.id}")


@command("pause", prefixes="/", chat_scope="group")
async def pause_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    ok, err = await _do_pause(message.chat.id)
    await message.reply_text(tr("music.playback_paused") if ok else err)


@command("resume", prefixes="/", chat_scope="group")
async def resume_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    ok, err = await _do_resume(message.chat.id)
    await message.reply_text(tr("music.playback_resumed") if ok else err)


@command("skip", prefixes="/", chat_scope="group")
async def skip_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    msg_dict, err = await _handle_skip(message.chat.id)
    if err:
        await message.reply_text(err)
    elif msg_dict:
        await _delete_old_playback_message(message.chat.id)
        if msg_dict.get("photo") is None:
            sent = await message.reply_text(
                msg_dict.get("caption", ""), reply_markup=msg_dict.get("reply_markup")
            )
        else:
            try:
                sent = await message.reply_photo(**msg_dict)
            except RPCError:
                sent = await message.reply_text(
                    msg_dict.get("caption", ""), reply_markup=msg_dict.get("reply_markup")
                )
        await set_playback_message_id(message.chat.id, sent.id)


@command(["end", "cend"], prefixes="/", chat_scope="group")
async def end_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    if not await _check_command_access(message, message.chat.id):
        return
    ok, err = await _do_stop(message.chat.id)
    if not ok:
        return await message.reply_text(err)
    await _delete_old_playback_message(message.chat.id)
    await message.reply_text(tr("music.playback_ended_and_queue_cleared"))


@command(["autoplay", "cplay"], prefixes="/", chat_scope="group")
@anonadmin_checker
async def autoplay_cmd_msg(client: Client, message: Message):
    if await _check_if_clone(client, message):
        return
    chat_id = message.chat.id
    user_id, _ = message_actor(message)
    if not await is_user_admin(message, chat_id=chat_id, user_id=user_id):
        return

    args = (message.text or "").split(None, 1)
    if len(args) < 2:
        current = await get_autoplay_setting_cached(chat_id)
        status_str = "enabled" if current else "disabled"
        return await message.reply_text(tr("music.autoplay_currently", status_str=status_str))

    action = args[1].strip().lower()
    if action in ("on", "yes", "enable", "true"):
        await autoplay_db(chat_id, True)
        await message.reply_text(tr("music.autoplay_enabled_when_the_queue_ends_recommended"))
    elif action in ("off", "no", "disable", "false"):
        await autoplay_db(chat_id, False)
        await message.reply_text(tr("music.autoplay_disabled"))
    else:
        await reply_usage(message)


@Client.on_chat_member_updated(filters.group, group=800)
async def _on_assistant_member_update(client: Client, update):
    try:
        me = await _assistant_me()
        user = getattr(update.old_chat_member, "user", None) or getattr(
            update.new_chat_member, "user", None
        )
        if user and user.id == me.id:
            new_status = getattr(update.new_chat_member, "status", None)
            if new_status in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED):
                await forget_assistant_membership(update.chat.id)
    except (RPCError, RedisError, OSError) as e:
        LOGGER.debug(
            "[Music] Assistant member update handler error for %s: %s",
            getattr(update.chat, "id", "?"),
            e,
        )
