import asyncio

import orjson
from pyrogram import Client, filters
from pyrogram.errors import MessageNotModified, RPCError
from pyrogram.types import CallbackQuery, Message

from Emilia.application import LOGGER, pgram, redis_client
from Emilia.config import Config
from Emilia.custom_filter import auth, callbackquery, command, listen
from Emilia.database import playlists as db
from Emilia.locales import tr
from Emilia.modules.music.playlist import core as plcore
from Emilia.modules.music.playlist import import_engine as imports
from Emilia.modules.music.playlist import social, ui
from Emilia.modules.music.playlist.utils import (
    LIMIT_CREATE,
    LIMIT_EXPORT,
    LIMIT_FORK,
    LIMIT_IMPORT,
    LIMIT_QR,
    LIMIT_REPORT,
    build_share_link,
    export_playlist,
    generate_qr,
    guard_action,
    limit_message,
    sanitize_text,
    validate_title,
)
from Emilia.utils import cb_token
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.errors import report_error
from Emilia.utils.forward_origin import fwd_user
from Emilia.utils.get_user import resolve_peer_target
from Emilia.utils.menu_guard import CallbackAccess, claim_tap, remember_menu
from Emilia.utils.message_actor import message_actor
from Emilia.utils.tasks import spawn

_PENDING_TTL = 300  # a prompt the user ignored shouldn't capture their next
# unrelated message ten minutes later


def _pending_key(user_id: int) -> str:
    return f"{Config.CACHE_NAMESPACE}:music:{Config.BOT_ID}:pl_pending:{user_id}"


async def _set_pending(user_id: int, action: str, pid: str = "") -> None:
    await redis_client.setex(
        _pending_key(user_id),
        _PENDING_TTL,
        orjson.dumps({"action": action, "pid": pid}).decode(),
    )


async def _get_pending(user_id: int):
    raw = await redis_client.get(_pending_key(user_id))
    return orjson.loads(raw) if raw else None


async def _clear_pending(user_id: int) -> None:
    await redis_client.delete(_pending_key(user_id))


async def _stash_track(track: dict, client, user_id, chat_id) -> str:
    return await cb_token.stash(
        track, ttl=_PENDING_TTL, client=client, user_id=user_id, chat_id=chat_id
    )


async def _stashed_track(token: str, client, query):
    return await cb_token.unstash(
        token, client=client, user_id=query.from_user.id, chat_id=query.message.chat.id
    )


async def send_menu(message: Message, text: str, markup=None) -> Message:
    """Reply with a menu and record who it belongs to, so nobody else can drive it."""
    sent = await message.reply_text(text, reply_markup=markup)
    actor_id, _ = message_actor(message)
    await remember_menu(sent, actor_id)
    return sent


async def _load_viewable(query: CallbackQuery, pid: str):
    """Fetch a playlist and confirm the tapper may see it."""
    pl = await db.get_playlist(pid)
    if not pl:
        await query.answer(tr("playlist.commands.that_playlist_no_longer_exists"), show_alert=True)
        return None
    if pl.get("banned"):
        await query.answer(tr("playlist.commands.that_playlist_has_been_removed"), show_alert=True)
        return None
    chat_id = query.message.chat.id if query.message else None
    if not plcore.can_view(pl, query.from_user.id, chat_id):
        await query.answer(tr("playlist.commands.you_don_t_have_access_to_that"), show_alert=True)
        return None
    return pl


async def _load_editable(query: CallbackQuery, pid: str):
    pl = await _load_viewable(query, pid)
    if not pl:
        return None
    if not plcore.can_edit(pl, query.from_user.id):
        await query.answer(tr("playlist.commands.you_can_t_edit_that_playlist"), show_alert=True)
        return None
    return pl


async def _edit(query: CallbackQuery, text: str, markup=None):
    if not await CallbackAccess().allows(query._client, query, notify=False):
        sent = await query.message.reply_text(text, reply_markup=markup)
        await remember_menu(sent, query.from_user.id, client=query._client)
        return sent
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except MessageNotModified:
        pass


async def _refresh_if_owner(query: CallbackQuery, pid: str) -> None:
    if not await CallbackAccess().allows(query._client, query, notify=False):
        return
    pl = await db.get_playlist(pid)
    if pl:
        await _show_view(query, pl)


async def _show_view(query: CallbackQuery, pl: dict, page: int = 0):
    text, markup = await ui.render_playlist_view(pl, query.from_user.id, query._client, page)
    await _edit(query, text, markup)


def _int(value: str, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _split_page_arg(arg: str):
    if "|" in arg:
        page_str, _, query = arg.partition("|")
        return _int(page_str), query
    return _int(arg), ""


@command("playlist")
@anonadmin_checker(named=True)
async def playlist_command(client: Client, message: Message):
    from Emilia.modules.music.play import _check_if_clone, playlist_cmd

    if await _check_if_clone(client, message):
        return

    parts = (message.text or "").split()
    if len(parts) > 1:
        # A link or ID queues the playlist in the current voice chat.
        return await playlist_cmd(client, message)

    user_id, _ = message_actor(message)
    in_group = message.chat.type.name != "PRIVATE"
    if in_group:
        # Opening your library from a group is the clearest statement of which
        # voice chat you mean, so Play works from PM later on too.
        await plcore.remember_group(user_id, message.chat.id)

    # Show first-time onboarding hint if user has zero playlists
    count = await db.count_user_playlists(user_id)
    first_time = count == 0

    text, markup = ui.render_root(user_id, in_group=in_group, first_time=first_time)
    await send_menu(message, text, markup)


def _public_playlist_action(client, query):
    verb, _, arg = ui.parse_cb(query.data)
    return verb == "noop" or (verb in _SOCIAL and (verb != "root" or arg == "new"))


@callbackquery(pattern=r"^pl:", access=CallbackAccess(public=_public_playlist_action))
async def playlist_callbacks(client: Client, query: CallbackQuery):
    if getattr(client, "is_clone", False):
        return await query.answer(
            tr("music.music_system_is_disabled_on_cloned_bots"), show_alert=True
        )
    verb, pid, arg = ui.parse_cb(query.data)
    user_id = query.from_user.id

    if verb == "noop":
        return await query.answer()

    handler = _ROUTES.get(verb)
    if handler is None:
        return await query.answer()

    if verb in _DEBOUNCED and not await claim_tap(user_id, query.data, client=client):
        return await query.answer(tr("playlist.commands.already_working_on_that"))

    try:
        await handler(client, query, pid, arg)
    except Exception as e:
        await report_error("playlists.callback", e, verb=verb, user=user_id)
        try:
            await query.answer(tr("custom_filter.something_went_wrong"), show_alert=True)
        except RPCError:
            pass


_SOCIAL = frozenset(
    {
        "like",
        "save",
        "fork",
        "play",
        "enqueue",
        "share",
        "qr",
        "export",
        "report",
        # "root" is on the shared Now Playing card, which nobody owns: any member who
        # taps Playlists there gets their own fresh menu (see _h_root's "new" arg).
        "root",
    }
)

_DEBOUNCED = frozenset({"qr", "play", "enqueue", "fork"})


async def _h_root(client, query, pid, arg):
    in_group = query.message.chat.type.name != "PRIVATE" if query.message else False
    text, markup = ui.render_root(query.from_user.id, in_group=in_group)

    if arg == "new" and query.message:
        await query.answer()
        await plcore.remember_group(query.from_user.id, query.message.chat.id)
        sent = await query.message.reply_text(text, reply_markup=markup)
        return await remember_menu(sent, query.from_user.id)

    await _edit(query, text, markup)
    await query.answer()


async def _h_lib(client, query, pid, arg):
    page = _int(arg)
    user_id = query.from_user.id
    total = await db.count_user_playlists(user_id)
    playlists = await db.get_user_playlists(user_id, skip=page * ui.PAGE_SIZE, limit=ui.PAGE_SIZE)
    text, markup = ui.render_library(playlists, page, total)
    await _edit(query, text, markup)
    await query.answer()


async def _h_trend(client, query, pid, arg):
    page, _ = _split_page_arg(arg)
    playlists = await plcore.get_trending(limit=ui.PAGE_SIZE, skip=page * ui.PAGE_SIZE)
    text, markup = ui.render_discovery(playlists, page, "trend")
    await _edit(query, text, markup)
    await query.answer()


async def _h_browse(client, query, pid, arg):
    page, _ = _split_page_arg(arg)
    playlists = await db.get_recent(limit=ui.PAGE_SIZE, skip=page * ui.PAGE_SIZE)
    text, markup = ui.render_discovery(playlists, page, "browse")
    await _edit(query, text, markup)
    await query.answer()


async def _h_saved(client, query, pid, arg):
    page, _ = _split_page_arg(arg)
    playlists = await db.get_saved_playlists(
        query.from_user.id, skip=page * ui.PAGE_SIZE, limit=ui.PAGE_SIZE
    )
    text, markup = ui.render_discovery(playlists, page, "saved")
    await _edit(query, text, markup)
    await query.answer()


async def _h_server(client, query, pid, arg):
    if not query.message or query.message.chat.type.name == "PRIVATE":
        return await query.answer(
            tr("playlist.commands.only_works_inside_a_group"), show_alert=True
        )
    page, _ = _split_page_arg(arg)
    playlists = await db.get_server_playlists(
        query.message.chat.id, skip=page * ui.PAGE_SIZE, limit=ui.PAGE_SIZE
    )
    text, markup = ui.render_discovery(playlists, page, "server")
    await _edit(query, text, markup)
    await query.answer()


async def _h_search(client, query, pid, arg):
    page, term = _split_page_arg(arg)
    playlists = await db.search(term, limit=ui.PAGE_SIZE, skip=page * ui.PAGE_SIZE)
    text, markup = ui.render_discovery(playlists, page, "search", term)
    await _edit(query, text, markup)
    await query.answer()


async def _h_view(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        await _show_view(query, pl, _int(arg))
        await query.answer()


async def _h_more(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.render_more(pl, query.from_user.id)
        await _edit(query, text, markup)
        await query.answer()


async def _h_manage(client, query, pid, arg):
    pl = await _load_editable(query, pid)
    if pl:
        text, markup = ui.render_manage(pl, query.from_user.id)
        await _edit(query, text, markup)
        await query.answer()


async def _h_liked(client, query, pid, arg):
    pl = await db.get_or_create_liked_playlist(query.from_user.id)
    if not pl:
        return await query.answer(
            tr("playlist.commands.could_not_open_liked_songs"), show_alert=True
        )
    await _show_view(query, pl)
    await query.answer()


async def _h_stats(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.simple_view(await social.render_stats(pid), pid)
        await _edit(query, text, markup)
        await query.answer()


async def _h_feed(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.simple_view(await social.render_activity_feed(pid), pid)
        await _edit(query, text, markup)
        await query.answer()


async def _h_lineage(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.simple_view(await social.render_lineage(pid), pid)
        await _edit(query, text, markup)
        await query.answer()


async def _h_like(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    liked = await db.toggle_like(pid, query.from_user.id)
    await query.answer("Liked." if liked else tr("playlist.commands.like_removed"))
    await _refresh_if_owner(query, pid)


async def _h_save(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    saved = await db.toggle_save(pid, query.from_user.id)
    await query.answer(
        tr("playlist.commands.saved_library")
        if saved
        else tr("playlist.commands.removed_from_saved")
    )
    await _refresh_if_owner(query, pid)


async def _h_fork(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    user_id = query.from_user.id
    if pl.get("owner_id") == user_id:
        return await query.answer(
            tr("playlist.commands.this_is_already_your_playlist"), show_alert=True
        )

    allowed, retry = await guard_action(user_id, "fork", LIMIT_FORK)
    if not allowed:
        return await query.answer(limit_message("fork", retry), show_alert=True)

    if await db.count_user_playlists(user_id) >= db.MAX_PLAYLISTS_PER_USER:
        return await query.answer(
            tr(
                "playlist.commands.ve_reached_limit_playlists_h_fork",
                max_playlists_per_user=db.MAX_PLAYLISTS_PER_USER,
            ),
            show_alert=True,
        )

    new_id = await plcore.fork_playlist(pid, user_id)
    if not new_id:
        return await query.message.reply_text(tr("playlist.commands.could_not_fork_that_playlist"))

    await query.answer(tr("playlist.commands.forked_into_your_library"))
    forked = await db.get_playlist(new_id)
    if forked:
        await _show_view(query, forked)


async def _say(client, query, chat_id: int, text: str):
    if query.message and query.message.chat.id == chat_id:
        return await query.message.reply_text(text)
    return await client.send_message(chat_id, text)


async def _resolve_target_chat(query):
    if query.message and query.message.chat.type.name != "PRIVATE":
        return query.message.chat.id, None

    chat_id = await plcore.recall_group(query.from_user.id)
    if not chat_id:
        return None, (tr("playlist.commands.open_from_group_re_listening_tap_playlists_player"))

    from Emilia.modules.music.utils.store import get_now_playing

    if not await get_now_playing(chat_id):
        return None, (tr("playlist.commands.there_s_no_voice_chat_playing_where_last"))
    return chat_id, None


async def _h_play(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return

    chat_id, error = await _resolve_target_chat(query)
    if not chat_id:
        return await query.answer(error, show_alert=True)

    songs = await db.get_songs(pid, limit=db.MAX_SONGS_PER_PLAYLIST)
    if not songs:
        return await query.answer(tr("playlist.commands.that_playlist_is_empty"), show_alert=True)

    from Emilia.modules.music.core.youtube import fetch_and_download
    from Emilia.modules.music.play import (
        PlaybackAccess,
        _start_playback,
        prefetch_next,
    )
    from Emilia.modules.music.utils.store import (
        add_many_to_queue,
        get_now_playing,
    )

    if not await PlaybackAccess(
        target_chat_id=chat_id,
        require_player_message=False,
        allow_idle=True,
        allow_admin=True,
        denial="playlist.commands.only_the_person_who_started_playback_or",
    ).allows(client, query):
        return

    tracks = [_song_to_track(s, query.from_user.id, query.from_user.mention) for s in songs]

    await query.answer(tr("playlist.commands.queueing_tracks", tracks=len(tracks)))

    if await get_now_playing(chat_id):
        await add_many_to_queue(chat_id, tracks)
        await _say(
            client,
            query,
            chat_id,
            tr(
                "playlist.commands.added_tracks_from_queue",
                songs=len(tracks),
                title=pl.get("title"),
            ),
        )
        spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
    else:
        first, rest = tracks[0], tracks[1:]
        if rest:
            await add_many_to_queue(chat_id, rest)
        status = await _say(
            client,
            query,
            chat_id,
            tr("playlist.commands.starting_loading_first_track", title=pl.get("title")),
        )
        try:
            first = await fetch_and_download(first["webpage_url"], False)
        except Exception as e:
            LOGGER.warning("[Playlist] Could not load first track of %s: %s", pid, e)
            return await status.edit_text(
                tr("playlist.commands.could_not_start_that_track_the_rest")
            )
        first["user_id"] = query.from_user.id
        first["requester_mention"] = query.from_user.mention
        await _start_playback(
            chat_id,
            first,
            query.from_user.mention,
            reply_message=status,
            user_id=query.from_user.id,
        )
        await status.delete()

    await plcore.session_start(chat_id, pid, query.from_user.id, len(tracks))


async def _h_enqueue(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return

    chat_id, error = await _resolve_target_chat(query)
    if not chat_id:
        return await query.answer(error, show_alert=True)

    songs = await db.get_songs(pid, limit=db.MAX_SONGS_PER_PLAYLIST)
    if not songs:
        return await query.answer(tr("playlist.commands.that_playlist_is_empty"), show_alert=True)

    from Emilia.modules.music.play import PlaybackAccess, prefetch_next
    from Emilia.modules.music.utils.store import add_many_to_queue

    if not await PlaybackAccess(
        target_chat_id=chat_id,
        require_player_message=False,
        allow_idle=True,
        allow_admin=True,
        denial="playlist.commands.only_the_person_who_started_playback_or",
    ).allows(client, query):
        return

    await add_many_to_queue(
        chat_id,
        [_song_to_track(s, query.from_user.id, query.from_user.mention) for s in songs],
    )
    spawn(prefetch_next(chat_id), name=f"prefetch_next:{chat_id}")
    await query.answer(tr("playlist.commands.queued_tracks", songs=len(songs)))
    await _say(
        client,
        query,
        chat_id,
        tr("playlist.commands.added_tracks_from_queue", songs=len(songs), title=pl.get("title")),
    )
    await plcore.session_start(chat_id, pid, query.from_user.id, len(songs))


def _song_to_track(song: dict, user_id: int = None, requester_mention: str = None) -> dict:
    return {
        "id": song.get("video_id"),
        "title": song.get("title"),
        "uploader": song.get("uploader"),
        "thumbnail": song.get("thumbnail"),
        "duration": song.get("duration"),
        "webpage_url": song.get("webpage_url"),
        "source": song.get("source", "youtube"),
        "user_id": user_id,
        "requester_mention": requester_mention,
    }


async def _h_share(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if pl:
        text, markup = ui.render_share(pl, build_share_link(pid))
        await _edit(query, text, markup)
        await query.answer()


async def _h_qr(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    allowed, retry = await guard_action(query.from_user.id, "qr", LIMIT_QR)
    if not allowed:
        return await query.answer(limit_message("QR", retry), show_alert=True)

    await query.answer(tr("playlist.commands.generating"))
    png = await asyncio.to_thread(generate_qr, pid, pl.get("title", ""))
    if not png:
        return await query.message.reply_text(tr("playlist.commands.could_not_build_that_qr_code"))

    await query.message.reply_photo(
        png,
        caption=(
            tr(
                "playlist.commands.scan_open_playlist",
                g_qr=ui.G_QR,
                title=pl.get("title", "Untitled"),
            )
        ),
    )


async def _h_export(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return

    if not arg:
        await query.answer()
        return await _edit(query, *ui.render_export_picker(pl))

    allowed, retry = await guard_action(query.from_user.id, "export", LIMIT_EXPORT)
    if not allowed:
        return await query.answer(limit_message("export", retry), show_alert=True)
    if not await claim_tap(query.from_user.id, query.data, client=client):
        return await query.answer(tr("playlist.commands.already_building_that"))

    await query.answer(tr("playlist.commands.building_your_file"))
    doc, error = await export_playlist(pid, arg)
    if error:
        return await query.message.reply_text(
            tr("playlist.commands.playlist_redirect_error", error=error)
        )

    await query.message.reply_document(
        doc,
        caption=tr("playlist.commands.export", title=pl.get("title", "Untitled"), arg=arg.upper()),
    )


async def _h_report(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    user_id = query.from_user.id
    if pl.get("owner_id") == user_id:
        return await query.answer(
            tr("playlist.commands.you_can_t_report_your_own_playlist"), show_alert=True
        )

    allowed, retry = await guard_action(user_id, "report", LIMIT_REPORT)
    if not allowed:
        return await query.answer(limit_message("report", retry), show_alert=True)

    filed = await db.report_playlist(pid, user_id, "user_report")
    if filed:
        try:
            reporter = query.from_user
            handle = f"@{reporter.username}" if reporter.username else reporter.mention
            await pgram.send_message(
                Config.EVENT_LOGS,
                tr(
                    "playlist.commands.playlist_report_id_owner_reported_review_plreports_ban",
                    title=pl.get("title", "Untitled"),
                    pid=pid,
                    owner_id=pl.get("owner_id"),
                    handle=handle,
                    user_id=user_id,
                    pid_2=pid,
                ),
            )
        except RPCError as e:
            LOGGER.warning("[Playlists] Could not forward report to log channel: %s", e)
    await query.answer(
        tr("playlist.commands.reported_moderators_will_review")
        if filed
        else tr("playlist.commands.ve_already_reported_playlist"),
        show_alert=True,
    )


@auth(pattern="plreports")
async def plreports_cmd(client: Client, message: Message):
    reports = await db.get_open_reports(limit=20)
    if not reports:
        return await message.reply_text(tr("playlist.commands.no_open_playlist_reports"))

    counts: dict = {}
    for r in reports:
        counts.setdefault(r["playlist_id"], 0)
        counts[r["playlist_id"]] += 1

    pls = await db.get_playlists_bulk(list(counts))
    lines = [tr("playlist.commands.open_playlist_reports"), ""]
    for pid, n in counts.items():
        pl = pls.get(pid)
        title = pl.get("title", "Untitled") if pl else "(deleted)"
        banned = tr("playlist.commands.already_banned") if pl and pl.get("banned") else ""
        lines.append(f"`•` **{title}** — {n} report{'s' if n != 1 else ''}{banned}\n   `{pid}`")
    lines.append(tr("playlist.commands.ban_plban_unban_plunban"))
    await message.reply_text("\n".join(lines))


@auth(pattern="plban")
async def plban_cmd(client: Client, message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        return await reply_usage(message)
    pid = parts[1]
    pl = await db.get_playlist(pid)
    if not pl:
        return await message.reply_text(tr("playlist.commands.no_playlist_with_that_id"))
    await db.set_banned(pid, True)
    await db.resolve_reports(pid)
    await message.reply_text(
        tr("playlist.commands.banned_cleared_its_reports", title=pl.get("title", "Untitled"))
    )


@auth(pattern="plunban")
async def plunban_cmd(client: Client, message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        return await reply_usage(message)
    pid = parts[1]
    pl = await db.get_playlist(pid)
    if not pl:
        return await message.reply_text(tr("playlist.commands.no_playlist_with_that_id"))
    await db.set_banned(pid, False)
    await message.reply_text(tr("playlist.commands.unbanned", title=pl.get("title", "Untitled")))


async def _h_access(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer(
            tr("playlist.commands.only_the_owner_can_change_access"), show_alert=True
        )
    text, markup = ui.render_access(pl)
    await _edit(query, text, markup)
    await query.answer()


async def _h_setaccess(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer(
            tr("playlist.commands.only_the_owner_can_change_access"), show_alert=True
        )
    if arg not in db.ACCESS_MODES:
        return await query.answer()

    updates = {"access_mode": arg}
    if arg == db.ACCESS_SERVER:
        if not query.message or query.message.chat.type.name == "PRIVATE":
            return await query.answer(
                tr("playlist.commands.set_server_only_from_inside_the_group"), show_alert=True
            )
        updates["server_chat_id"] = query.message.chat.id

    await db.update_playlist(pid, updates)
    await social.log(pid, query.from_user.id, "access_changed", mode=arg)
    await query.answer(tr("playlist.commands.access_set", arg=ui.MODE_LABEL.get(arg, arg)))

    refreshed = await db.get_playlist(pid)
    if refreshed:
        text, markup = ui.render_access(refreshed)
        await _edit(query, text, markup)


async def _h_delprompt(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer(
            tr("playlist.commands.only_the_owner_can_delete_this"), show_alert=True
        )
    text, markup = ui.render_delete_confirm(pl)
    await _edit(query, text, markup)
    await query.answer()


async def _h_delete(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer(
            tr("playlist.commands.only_the_owner_can_delete_this"), show_alert=True
        )

    await db.delete_playlist(pid)
    await query.answer(tr("playlist.commands.playlist_deleted"))
    text, markup = ui.render_library(
        await db.get_user_playlists(query.from_user.id, limit=ui.PAGE_SIZE),
        0,
        await db.count_user_playlists(query.from_user.id),
    )
    await _edit(query, text, markup)


async def _h_rmsong(client, query, pid, arg):
    pl = await _load_editable(query, pid)
    if not pl:
        return

    if arg.startswith("p"):
        removed = await db.remove_song(pid, _int(arg[1:], -1))
        if removed:
            await social.log(pid, query.from_user.id, "removed_song", title=removed.get("title"))
            await query.answer(tr("playlist.commands.removed", title=removed.get("title", "track")))
        else:
            await query.answer(tr("playlist.commands.that_track_is_already_gone"))
        pl = await db.get_playlist(pid)
        arg = "0"
    else:
        await query.answer()

    await _render_picker(query, pl, "rmsong", _int(arg))


async def _h_reorder(client, query, pid, arg):
    pl = await _load_editable(query, pid)
    if not pl:
        return

    if arg.startswith("u"):
        position = _int(arg[1:], 0)
        if position > 1:
            await db.move_song(pid, position, position - 1)
            await social.log(pid, query.from_user.id, "moved_song", position=position)
            await query.answer(tr("playlist.commands.moved_up"))
        else:
            await query.answer(tr("playlist.commands.already_first"))
        pl = await db.get_playlist(pid)
        arg = "0"
    else:
        await query.answer()

    await _render_picker(query, pl, "reorder", _int(arg))


async def _render_picker(query, pl, mode: str, page: int):
    songs = await db.get_songs(
        pl["playlist_id"], skip=page * ui.SONG_PAGE_SIZE, limit=ui.SONG_PAGE_SIZE
    )
    await _edit(query, *ui.render_song_picker(pl, songs, page, mode))


async def _h_editors(client, query, pid, arg):
    pl = await _load_viewable(query, pid)
    if not pl:
        return
    if pl.get("owner_id") != query.from_user.id:
        return await query.answer(
            tr("playlist.commands.only_owner_manages_editors"), show_alert=True
        )

    if arg.startswith("r"):
        removed_id = _int(arg[1:], 0)
        if removed_id:
            await db.remove_editor(pid, removed_id)
            await social.log(pid, query.from_user.id, "editor_removed", target=removed_id)
            await query.answer(tr("playlist.commands.editor_removed"))
        pl = await db.get_playlist(pid)
    else:
        await query.answer()

    names = await social.resolve_names(pl.get("editors", []) or [])
    await _edit(query, *ui.render_editors(pl, names))


async def _h_dupreplace(client, query, pid, arg):
    pl = await _load_editable(query, pid)
    if not pl:
        return
    track = await _stashed_track(arg, client, query)
    if not track:
        return await query.answer(
            tr("playlist.commands.that_prompt_expired_add_it_again"), show_alert=True
        )

    video_id = track.get("video_id") or track.get("id")
    ok = await plcore.replace_duplicate(pid, video_id, track, query.from_user.id)
    await query.answer("Replaced." if ok else tr("playlist.commands.could_not_replace_track"))
    refreshed = await db.get_playlist(pid)
    if refreshed:
        await _show_view(query, refreshed)


async def _h_dupskip(client, query, pid, arg):
    await _stashed_track(arg, client, query)
    await query.answer(tr("playlist.commands.skipped"))
    pl = await _load_viewable(query, pid)
    if pl:
        await _show_view(query, pl)


_CANCEL_HINT = tr("playlist.commands.cancel_stop")

_PROMPTS = {
    "newprompt": (
        "new",
        tr("playlist.commands.new_playlist_send_name", g_add=ui.G_ADD) + _CANCEL_HINT,
    ),
    "searchprompt": (
        "search",
        tr("playlist.commands.search_send_playlist_name_look", g_search=ui.G_SEARCH) + _CANCEL_HINT,
    ),
    "addprompt": (
        "add",
        tr("playlist.commands.add_music_send_song_name_youtube_spotify_link", g_add=ui.G_ADD)
        + _CANCEL_HINT,
    ),
    "rename": (
        "rename",
        tr("playlist.commands.rename_send_new_name", g_edit=ui.G_EDIT) + _CANCEL_HINT,
    ),
    "redesc": (
        "redesc",
        tr("playlist.commands.description_send_new_description", g_edit=ui.G_EDIT) + _CANCEL_HINT,
    ),
    "addeditor": (
        "addeditor",
        tr("playlist.commands.add_editor_forward_message_from_them_send_their", g_add=ui.G_ADD)
        + _CANCEL_HINT,
    ),
}


async def _h_prompt(client, query, pid, arg):
    verb, _, _ = ui.parse_cb(query.data)
    action, text = _PROMPTS[verb]

    if action in ("add", "rename", "redesc", "addeditor"):
        if not await _load_editable(query, pid):
            return

    await _set_pending(query.from_user.id, action, pid)

    if query.message and query.message.chat.type.name != "PRIVATE":
        await _edit(query, *ui.render_pm_handoff(text))
        return await query.answer(tr("playlist.commands.continue_in_my_pm"), show_alert=True)

    await _edit(query, *ui.render_prompt(text, pid))
    await query.answer()


@command("cancel")
async def cancel_pending_cmd(client: Client, message: Message):
    if getattr(client, "is_clone", False):
        return
    if not message.from_user:
        return

    pending = await _get_pending(message.from_user.id)
    if pending:
        await _clear_pending(message.from_user.id)
        await message.reply_text(tr("clone.cancelled"))
    else:
        await message.reply_text(tr("playlist.commands.nothing_to_cancel"))


@listen(filters=filters.private & filters.incoming & filters.text)
async def playlist_text_input(client: Client, message: Message):
    if getattr(client, "is_clone", False):
        return
    if not message.from_user:
        return

    user_id = message.from_user.id
    pending = await _get_pending(user_id)
    if not pending:
        return

    text = (message.text or "").strip()
    if text.lower() in ("/cancel", "cancel"):
        await _clear_pending(user_id)
        return await message.reply_text(tr("playlist.commands.cancelled"))
    if text.startswith("/"):
        # Another command means they've moved on; don't swallow it.
        return

    action, pid = pending.get("action"), pending.get("pid", "")
    await _clear_pending(user_id)

    handler = _INPUT_ROUTES.get(action)
    if handler:
        try:
            await handler(client, message, pid, text)
        except Exception as e:
            await report_error("playlists.input", e, action=action, user=user_id)
            await message.reply_text(tr("playlist.commands.something_went_wrong"))


async def _i_new(client, message, pid, text):
    user_id = message.from_user.id

    allowed, retry = await guard_action(user_id, "create", LIMIT_CREATE)
    if not allowed:
        return await message.reply_text(limit_message("create", retry))

    title, error = validate_title(text)
    if error:
        return await message.reply_text(
            tr("playlist.commands.playlist_redirect_error", error=error)
        )

    if await db.count_user_playlists(user_id) >= db.MAX_PLAYLISTS_PER_USER:
        return await message.reply_text(
            tr(
                "playlist.commands.ve_reached_limit_playlists",
                max_playlists_per_user=db.MAX_PLAYLISTS_PER_USER,
            )
        )

    pl = await db.create_playlist(user_id, title)
    if not pl:
        return await message.reply_text(tr("playlist.commands.could_not_create_that_playlist"))

    view_text, markup = await ui.render_playlist_view(pl, user_id, client)
    await send_menu(message, view_text, markup)


async def _i_search(client, message, pid, text):
    term = sanitize_text(text, max_len=64)
    playlists = await db.search(term, limit=ui.PAGE_SIZE)
    view_text, markup = ui.render_discovery(playlists, 0, "search", term)
    await send_menu(message, view_text, markup)


async def _i_rename(client, message, pid, text):
    pl = await db.get_playlist(pid)
    if not pl or not plcore.can_edit(pl, message.from_user.id):
        return await message.reply_text(tr("playlist.commands.can_t_edit_playlist"))

    title, error = validate_title(text)
    if error:
        return await message.reply_text(
            tr("playlist.commands.playlist_redirect_error", error=error)
        )

    await db.update_playlist(pid, {"title": title})
    await social.log(pid, message.from_user.id, "renamed", title=title)
    refreshed = await db.get_playlist(pid)
    view_text, markup = await ui.render_playlist_view(refreshed, message.from_user.id, client)
    await send_menu(message, view_text, markup)


async def _i_redesc(client, message, pid, text):
    pl = await db.get_playlist(pid)
    if not pl or not plcore.can_edit(pl, message.from_user.id):
        return await message.reply_text(tr("playlist.commands.can_t_edit_playlist"))

    description = sanitize_text(text, max_len=200)
    await db.update_playlist(pid, {"description": description})
    await social.log(pid, message.from_user.id, "described")
    refreshed = await db.get_playlist(pid)
    view_text, markup = await ui.render_playlist_view(refreshed, message.from_user.id, client)
    await send_menu(message, view_text, markup)


async def _i_addeditor(client, message, pid, text):
    pl = await db.get_playlist(pid)
    if not pl or pl.get("owner_id") != message.from_user.id:
        return await message.reply_text(tr("playlist.commands.only_the_owner_manages_editors"))

    forwarded_user = fwd_user(message)
    user = await resolve_peer_target(client, forwarded_user or text.strip())
    if user is None:
        return await message.reply_text(
            tr("playlist.commands.couldn_t_identify_that_user_forward_one")
        )
    target = user.id
    if target == pl.get("owner_id"):
        return await message.reply_text(tr("playlist.commands.you_already_own_this_playlist"))

    await db.add_editor(pid, target)
    await social.log(pid, message.from_user.id, "editor_added", target=target)
    name = await social.resolve_name(target)
    await message.reply_text(tr("playlist.commands.can_now_edit_playlist", name=name))


async def _i_add(client, message, pid, text):
    user_id = message.from_user.id
    pl = await db.get_playlist(pid)
    if not pl or not plcore.can_edit(pl, user_id):
        return await message.reply_text(tr("playlist.commands.can_t_edit_playlist"))

    kind, _ = imports.detect_source(text)

    if kind in ("yt_playlist", "sp_playlist", "sp_album"):
        return await _bulk_import(client, message, pl, text, kind)

    status_msg = await message.reply_text(
        tr("playlist.commands.looking_up", looking_up=sanitize_text(text, 80))
    )

    if kind:
        tracks, error = await imports.import_tracks(text)
        if error:
            return await status_msg.edit_text(
                tr("playlist.commands.playlist_redirect_error", error=error)
            )
        track = tracks[0] if tracks else None
    else:
        from Emilia.modules.music.core.youtube import search_youtube

        results = await search_youtube(text, limit=1)
        track = results[0] if results else None

    if not track:
        return await status_msg.edit_text(tr("playlist.commands.nothing_found_for_that"))

    status, position, existing = await plcore.add_song_with_prompt(pid, track, user_id)

    if status == "duplicate":
        token = await _stash_track(track, client, user_id, message.chat.id)
        prompt_text, markup = ui.render_duplicate_prompt(pl, existing, track, token)
        await remember_menu(status_msg, user_id, client=client)
        return await status_msg.edit_text(prompt_text, reply_markup=markup)
    if status == "full":
        return await status_msg.edit_text(
            tr(
                "playlist.commands.playlist_full_songs",
                max_songs_per_playlist=db.MAX_SONGS_PER_PLAYLIST,
            )
        )
    if status != "added":
        return await status_msg.edit_text(tr("playlist.commands.could_not_add_that_track"))

    await status_msg.edit_text(
        tr(
            "playlist.commands.added_at_position",
            title=track.get("title", "track"),
            position=position,
        )
    )


async def _bulk_import(client, message, pl, text, kind):
    user_id = message.from_user.id
    pid = pl["playlist_id"]

    allowed, retry = await guard_action(user_id, "import", LIMIT_IMPORT)
    if not allowed:
        return await message.reply_text(limit_message("import", retry))

    label = imports.source_label(kind)
    status_msg = await message.reply_text(tr("playlist.commands.reading", label=label))
    reporter = imports.ProgressReporter(status_msg, label=f"Importing {label}")

    tracks, error = await imports.import_tracks(text, progress=reporter.update)
    await reporter.flush()

    if error:
        return await status_msg.edit_text(
            tr("playlist.commands.playlist_redirect_error", error=error)
        )
    if not tracks:
        return await status_msg.edit_text(tr("playlist.commands.nothing_importable_at_that_link"))

    added, skipped = await plcore.import_tracks_bulk(pid, tracks, user_id)

    summary = [tr("playlist.commands.import_complete", g_library=ui.G_LIBRARY), ""]
    summary.append(
        tr("playlist.commands.added_track", added=added, added_track="s" if added != 1 else "")
    )
    if skipped:
        summary.append(tr("playlist.commands.skipped_already_playlist", skipped=skipped))
    if kind.startswith("sp_"):
        summary.append(tr("playlist.commands.spotify_tracks_matched_their_closest_audio_youtube"))

    refreshed = await db.get_playlist(pid)
    view_text, markup = await ui.render_playlist_view(refreshed, user_id, client)
    await status_msg.edit_text("\n".join(summary))
    await send_menu(message, view_text, markup)


@callbackquery(pattern=r"^pl_like:", access=CallbackAccess(public=True))
async def auto_like_callback(client: Client, query: CallbackQuery):
    user_id = query.from_user.id
    video_id = query.data.split(":", 1)[1] if ":" in query.data else ""
    if not video_id:
        return await query.answer()

    track = await _find_live_track(query.message.chat.id, video_id)
    if not track:
        return await query.answer(
            tr("playlist.commands.that_track_is_no_longer_playing_open"),
            show_alert=True,
        )

    await plcore.remember_group(user_id, query.message.chat.id)

    pl = await db.get_or_create_liked_playlist(user_id)
    if not pl:
        return await query.answer(
            tr("playlist.commands.could_not_open_your_liked_songs"), show_alert=True
        )

    pid = pl["playlist_id"]
    status, position = await db.toggle_song(pid, track, user_id)

    if status == "removed":
        return await query.answer(tr("playlist.commands.removed_from_liked_songs"))
    if status == "full":
        return await query.answer(
            tr(
                "playlist.commands.liked_songs_full",
                max_songs_per_playlist=db.MAX_SONGS_PER_PLAYLIST,
            ),
            show_alert=True,
        )
    if status != "added":
        return await query.answer(
            tr("playlist.commands.could_not_save_that_track"), show_alert=True
        )

    if position == 1:
        return await query.answer(
            tr("playlist.commands.saved_to_your_liked_songs_send_playlist"),
            show_alert=True,
        )

    await query.answer(tr("playlist.commands.saved_liked_songs", position=position))


async def _find_live_track(chat_id: int, video_id: str):
    from Emilia.modules.music.utils.store import get_now_playing, get_queue

    now = await get_now_playing(chat_id)
    if now and (now.get("id") == video_id):
        return now
    for track in await get_queue(chat_id) or []:
        if track.get("id") == video_id:
            return track
    return None


_ROUTES = {
    "root": _h_root,
    "lib": _h_lib,
    "trend": _h_trend,
    "browse": _h_browse,
    "saved": _h_saved,
    "server": _h_server,
    "search": _h_search,
    "view": _h_view,
    "more": _h_more,
    "manage": _h_manage,
    "liked": _h_liked,
    "stats": _h_stats,
    "feed": _h_feed,
    "lineage": _h_lineage,
    "like": _h_like,
    "save": _h_save,
    "fork": _h_fork,
    "play": _h_play,
    "enqueue": _h_enqueue,
    "share": _h_share,
    "qr": _h_qr,
    "export": _h_export,
    "report": _h_report,
    "access": _h_access,
    "setaccess": _h_setaccess,
    "delprompt": _h_delprompt,
    "delete": _h_delete,
    "rmsong": _h_rmsong,
    "reorder": _h_reorder,
    "editors": _h_editors,
    "dupreplace": _h_dupreplace,
    "dupskip": _h_dupskip,
    "newprompt": _h_prompt,
    "searchprompt": _h_prompt,
    "addprompt": _h_prompt,
    "rename": _h_prompt,
    "redesc": _h_prompt,
    "addeditor": _h_prompt,
}

_INPUT_ROUTES = {
    "new": _i_new,
    "search": _i_search,
    "add": _i_add,
    "rename": _i_rename,
    "redesc": _i_redesc,
    "addeditor": _i_addeditor,
}
