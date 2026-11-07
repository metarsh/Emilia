from pymongo.errors import PyMongoError
from pyrogram.errors import RPCError
from redis.exceptions import RedisError

from Emilia.application import LOGGER
from Emilia.locales import tr
from Emilia.modules.music.playlist.ui import render_playlist_view
from Emilia.modules.music.playlist.utils import (
    parse_deeplink,
    resolve_shared_playlist,
)


async def playlist_redirect(client, message):
    """
    Handle `t.me/<bot>?start=pl_<id>`.
    """
    user_id = message.from_user.id
    payload = message.text.split()[1]
    playlist_id = parse_deeplink(payload)

    if not playlist_id:
        return await message.reply_text(tr("playlist.links.that_playlist_link_is_malformed"))

    pl, error = await resolve_shared_playlist(playlist_id, user_id)
    if error:
        return await message.reply_text(
            tr("playlist.commands.playlist_redirect_error", error=error)
        )

    try:
        text, markup = await render_playlist_view(pl, user_id, client)
    except (RPCError, PyMongoError, RedisError, OSError) as e:
        LOGGER.error(f"[Playlists] deeplink render failed for {playlist_id}: {e}", exc_info=True)
        return await message.reply_text(tr("playlist.links.could_not_open_that_playlist"))

    from Emilia.modules.music.playlist.commands import send_menu

    await send_menu(message, text, markup)


async def playlist_menu_redirect(client, message):
    """
    Handle `t.me/<bot>?start=playlists` from the Now Playing "Playlists" button.
    """
    from Emilia.database import playlists as db
    from Emilia.modules.music.playlist import ui
    from Emilia.modules.music.playlist.commands import send_menu

    user_id = message.from_user.id
    count = await db.count_user_playlists(user_id)
    first_time = count == 0

    text, markup = ui.render_root(
        user_id,
        in_group=False,  # Deep-link always lands in PM
        first_time=first_time,
    )
    await send_menu(message, text, markup)
