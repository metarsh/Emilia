import logging
import random

from ntgcalls import BaseRTCException
from pyrogram.errors import ChannelPrivate, FloodWait, RPCError, UserNotParticipant
from pytgcalls import filters
from pytgcalls.exceptions import (
    ClientNotStarted,
    MTProtoClientNotConnected,
    NoActiveGroupCall,
    NotInCallError,
)
from pytgcalls.types import ChatUpdate, StreamEnded

from Emilia.application import pgram
from Emilia.database.chats_settings import get_autoplay_setting_cached
from Emilia.locales import tr
from Emilia.modules.music.core.call import emilia_call
from Emilia.modules.music.core.youtube import (
    ensure_local_file,
    get_related_tracks,
    search_youtube,
)
from Emilia.modules.music.play import (
    _build_caption,
    _build_playback_markup,
    _clear_stream_end_state,
    _delete_old_playback_message,
    _make_stream,
    _safe_play,
    _stream_end_ready,
    forget_assistant_membership,
    prefetch_next,
)
from Emilia.modules.music.playlist.core import (
    session_finish,
    session_track_finished,
)
from Emilia.modules.music.utils.store import (
    clear_autoplay_queue,
    clear_queue,
    get_loop_mode,
    get_now_playing,
    get_queue,
    get_shuffle_mode,
    pop_autoplay_next,
    pop_next,
    set_autoplay_queue,
    set_now_playing,
    set_paused,
    set_playback_message_id,
    set_queue_direct,
)
from Emilia.utils.errors import report_error
from Emilia.utils.tasks import spawn

LOGGER = logging.getLogger(__name__)


async def _send_now_playing_message(
    chat_id, track_info, mention, prefix=tr("music.events.playing_now")
):
    cap = _build_caption(track_info, mention, prefix)
    markup = _build_playback_markup(track_info, chat_id)
    thumb = track_info.get("thumbnail")
    try:
        sent = await pgram.send_photo(
            chat_id=chat_id,
            photo=thumb,
            caption=cap,
            reply_markup=markup,
        )
    except (RPCError, OSError):
        sent = await pgram.send_message(
            chat_id=chat_id,
            text=cap,
            reply_markup=markup,
        )
    if sent:
        await set_playback_message_id(chat_id, sent.id)


@emilia_call.on_update(filters.stream_end())
async def on_stream_end_handler(client, update: StreamEnded):
    chat_id = update.chat_id
    if not _stream_end_ready(chat_id, update.stream_type):
        LOGGER.debug(
            "[Music] Waiting for remaining stream end for chat %s: %s",
            chat_id,
            update.stream_type,
        )
        return
    try:
        LOGGER.info("[Music] Stream ended for chat %s", chat_id)
        await session_track_finished(chat_id)

        now = await get_now_playing(chat_id)
        loop_mode = await get_loop_mode(chat_id)
        shuffle = await get_shuffle_mode(chat_id)

        # Loop "one": replay current track
        if loop_mode == "one" and now:
            try:
                now = await ensure_local_file(now)
                await _safe_play(chat_id, _make_stream(now))
                await set_now_playing(chat_id, now)
                await set_paused(chat_id, False)
                spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
                await _delete_old_playback_message(chat_id)
                await _send_now_playing_message(
                    chat_id, now, now.get("requester_mention") or "User", "**Replaying**"
                )
                LOGGER.info("[Music] Replaying track in loop one for %s", chat_id)
            except (ChannelPrivate, UserNotParticipant):
                LOGGER.warning("[Music] Assistant lost membership during loop one for %s", chat_id)
                await forget_assistant_membership(chat_id)
                await set_now_playing(chat_id, None)
            except FloodWait as e:
                await report_error(
                    "music.stream_end.loop_one.flood_wait",
                    e,
                    chat_id=chat_id,
                    track=now.get("title"),
                    wait_seconds=e.value,
                )
                await set_now_playing(chat_id, None)
            except Exception as e:
                await report_error(
                    "music.stream_end.loop_one", e, chat_id=chat_id, track=now.get("title")
                )
                await set_now_playing(chat_id, None)
            return

        prev_settings = {}
        if now:
            prev_settings = {
                "loop_mode": now.get("loop_mode", "off"),
                "shuffle": now.get("shuffle", False),
            }
        nxt = await pop_next(chat_id)
        LOGGER.info(
            "[Music] Popped next track for chat %s: %s", chat_id, nxt.get("title") if nxt else None
        )

        # Loop "all" with empty queue: replay current
        if not nxt and loop_mode == "all" and now:
            nxt = now
            await set_now_playing(chat_id, nxt)
            try:
                nxt = await ensure_local_file(nxt)
                await _safe_play(chat_id, _make_stream(nxt))
                await set_paused(chat_id, False)
                spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
                await _delete_old_playback_message(chat_id)
                await _send_now_playing_message(
                    chat_id, nxt, nxt.get("requester_mention") or "User", "**Replaying**"
                )
                LOGGER.info("[Music] Replaying track in loop all for %s", chat_id)
            except (ChannelPrivate, UserNotParticipant):
                LOGGER.warning("[Music] Assistant lost membership during loop all for %s", chat_id)
                await forget_assistant_membership(chat_id)
                await set_now_playing(chat_id, None)
            except FloodWait as e:
                await report_error(
                    "music.stream_end.loop_all.flood_wait",
                    e,
                    chat_id=chat_id,
                    track=nxt.get("title"),
                    wait_seconds=e.value,
                )
                await set_now_playing(chat_id, None)
            except Exception as e:
                await report_error(
                    "music.stream_end.loop_all", e, chat_id=chat_id, track=nxt.get("title")
                )
                await set_now_playing(chat_id, None)
            return
        elif not nxt:
            if loop_mode != "all" and await get_autoplay_setting_cached(chat_id):
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
                        nxt.setdefault("loop_mode", prev_settings.get("loop_mode", "off"))
                        nxt.setdefault("shuffle", prev_settings.get("shuffle", False))
                        LOGGER.info(
                            "[Music] Autoplay picked next track for %s: %s",
                            chat_id,
                            nxt.get("title"),
                        )
                        await _play_next_available(chat_id, nxt, prev_settings)
                        return
                except Exception as e:
                    LOGGER.warning("[Music] Autoplay fetch failed for %s: %s", chat_id, e)

            await _end_playback(chat_id)
            LOGGER.info("[Music] Queue empty for chat %s, leaving call", chat_id)
            return

        await clear_autoplay_queue(chat_id)

        if shuffle:
            remaining = await get_queue(chat_id)
            if len(remaining) > 1:
                random.shuffle(remaining)
                await set_queue_direct(chat_id, remaining)

        nxt.setdefault("loop_mode", prev_settings.get("loop_mode", "off"))
        nxt.setdefault("shuffle", prev_settings.get("shuffle", False))

        await _play_next_available(chat_id, nxt, prev_settings)
    except Exception as e:
        await report_error("music.stream_end", e, chat_id=chat_id)


async def _play_next_available(chat_id, track, prev_settings, attempts: int = 3):
    for _ in range(attempts):
        track.setdefault("loop_mode", prev_settings.get("loop_mode", "off"))
        track.setdefault("shuffle", prev_settings.get("shuffle", False))
        try:
            track = await ensure_local_file(track)
            await _safe_play(chat_id, _make_stream(track))
        except (ChannelPrivate, UserNotParticipant):
            LOGGER.warning("[Music] Assistant lost membership during autoplay for %s", chat_id)
            await forget_assistant_membership(chat_id)
            await pgram.send_message(
                chat_id, tr("music.events.music_assistant_left_or_was_removed_from")
            )
            break
        except FloodWait as e:
            await report_error(
                "music.autoplay.flood_wait",
                e,
                chat_id=chat_id,
                track=track.get("title"),
                wait_seconds=e.value,
            )
            await pgram.send_message(chat_id, tr("music.events.i_couldn_t_load_the_next_track"))
            break
        except Exception as e:
            title = track.get("title", tr("music.events.track"))
            if isinstance(e, ValueError):
                LOGGER.warning("[Music] Could not fetch %s for %s: %s", title, chat_id, e)
            else:
                await report_error("music.autoplay", e, chat_id=chat_id, track=title)
            await pgram.send_message(
                chat_id, tr("music.events.skipping_couldn_t_load", title=title)
            )
            track = await pop_next(chat_id)
            if not track:
                break
            continue

        await set_now_playing(chat_id, track)
        await set_paused(chat_id, False)
        spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
        await _delete_old_playback_message(chat_id)
        await _send_now_playing_message(
            chat_id,
            track,
            track.get("requester_mention") or "User",
            tr("music.events.playing_now"),
        )
        LOGGER.info("[Music] Now playing next track in %s: %s", chat_id, track.get("title"))
        return

    await _end_playback(chat_id, tr("music.events.nothing_left_queue_could_play_stopping"))


async def _end_playback(chat_id, notice: str = None):
    _clear_stream_end_state(chat_id)
    await session_finish(chat_id)
    await _delete_old_playback_message(chat_id)
    await set_now_playing(chat_id, None)
    await set_paused(chat_id, False)
    try:
        await emilia_call.leave_call(chat_id)
    except NotInCallError:
        pass
    except (
        RPCError,
        OSError,
        BaseRTCException,
        NoActiveGroupCall,
        ClientNotStarted,
        MTProtoClientNotConnected,
    ) as e:
        LOGGER.error("[Music] Failed to leave call in %s: %s", chat_id, e)
    if notice:
        await pgram.send_message(chat_id, notice)


@emilia_call.on_update(
    filters.chat_update(
        ChatUpdate.Status.KICKED
        | ChatUpdate.Status.LEFT_GROUP
        | ChatUpdate.Status.CLOSED_VOICE_CHAT
    )
)
async def on_chat_update_handler(client, update: ChatUpdate):
    _clear_stream_end_state(update.chat_id)
    await session_finish(update.chat_id)
    await clear_queue(update.chat_id)
    await set_now_playing(update.chat_id, None)
    await set_playback_message_id(update.chat_id, None)
    if update.status in (ChatUpdate.Status.KICKED, ChatUpdate.Status.LEFT_GROUP):
        await forget_assistant_membership(update.chat_id)
