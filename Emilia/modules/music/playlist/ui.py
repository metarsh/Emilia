import asyncio

from pyrogram import Client
from pyrogram.enums import ButtonStyle
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from Emilia.database import playlists as db
from Emilia.locales import tr
from Emilia.modules.music.playlist.core import (
    MODE_GLYPH,
    MODE_LABEL,
    build_playlist_caption,
    format_duration,
)
from Emilia.modules.music.playlist.utils import EXPORT_FORMATS
from Emilia.utils.client_context import bot_username

G_LIBRARY = "⌘"
G_SAVE = "⭳"
G_LIKE = "♡"
G_LIKED = "♥"
G_FORK = "⑂"
G_SEARCH = "⌕"
G_TREND = "▲"
G_QUEUE = "≡"
G_MORE = "⋮"
G_EDIT = "✎"
G_DELETE = "✕"
G_PREV = "‹"
G_NEXT = "›"
G_BACK = "⟲"
G_SHARE = "⇱"
G_EXPORT = "⇩"
G_PLAY = "▷"
G_ADD = "＋"
G_STATS = "◫"
G_FEED = "◷"
G_REPORT = "⚑"
G_QR = "▦"
G_LINEAGE = "⋔"
G_BROWSE = "◎"

PAGE_SIZE = 8
SONG_PAGE_SIZE = 10

NOOP = "pl:noop"


def cb(verb: str, pid: str = "", arg: str = "") -> str:
    """Build callback data: pl:<verb>:<pid>:<arg>"""
    return f"pl:{verb}:{pid}:{arg}"


def parse_cb(data: str) -> tuple[str, str, str]:
    """
    Split callback data into (verb, pid, arg)
    """
    parts = data.split(":", 3)
    while len(parts) < 4:
        parts.append("")
    return parts[1], parts[2], parts[3]


def pager_row(
    verb: str,
    page: int,
    total_pages: int,
    pid: str = "",
) -> list[InlineKeyboardButton]:
    if total_pages <= 1:
        return []

    row = []
    if page > 0:
        row.append(InlineKeyboardButton(G_PREV, callback_data=cb(verb, pid, str(page - 1))))
    else:
        row.append(InlineKeyboardButton(" ", callback_data=NOOP))

    row.append(
        InlineKeyboardButton(
            tr("music.build_menu_markup_idx_total", idx=page + 1, total=total_pages),
            callback_data=NOOP,
        )
    )

    if page < total_pages - 1:
        row.append(InlineKeyboardButton(G_NEXT, callback_data=cb(verb, pid, str(page + 1))))
    else:
        row.append(InlineKeyboardButton(" ", callback_data=NOOP))

    return row


def _total_pages(count: int, per_page: int) -> int:
    if count <= 0:
        return 1
    return (count + per_page - 1) // per_page


def render_root(
    user_id: int, in_group: bool = False, first_time: bool = False
) -> tuple[str, InlineKeyboardMarkup]:
    if first_time:
        text = tr(
            "playlist.ui.playlists_create_playlists_save_songs_share_anyone_tap",
            g_library=G_LIBRARY,
        )
    else:
        text = tr(
            "playlist.ui.playlists_build_playlists_share_them_link_stream_any", g_library=G_LIBRARY
        )

    rows = [
        [
            InlineKeyboardButton(
                tr("playlist.ui.new_playlist", g_add=G_ADD),
                callback_data=cb("newprompt"),
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                tr("playlist.ui.liked_songs", g_liked=G_LIKED),
                callback_data=cb("liked"),
                style=ButtonStyle.PRIMARY,
            ),
        ],
        [
            InlineKeyboardButton(
                tr("playlist.ui.library", g_library=G_LIBRARY),
                callback_data=cb("lib", "", "0"),
            ),
            InlineKeyboardButton(
                tr("playlist.ui.saved", g_save=G_SAVE), callback_data=cb("saved", "", "0")
            ),
        ],
        [
            InlineKeyboardButton(
                tr("playlist.ui.browse_all_render_root", g_browse=G_BROWSE),
                callback_data=cb("browse", "", "0"),
                style=ButtonStyle.PRIMARY,
            ),
            InlineKeyboardButton(
                tr("playlist.ui.trending", g_trend=G_TREND),
                callback_data=cb("trend", "", "0"),
            ),
        ],
        [
            InlineKeyboardButton(
                tr("playlist.ui.search", g_search=G_SEARCH), callback_data=cb("searchprompt")
            ),
        ],
    ]
    if in_group:
        rows.append(
            [
                InlineKeyboardButton(
                    tr(
                        "playlist.ui.group_playlists_render_root",
                        mode_glyph=MODE_GLYPH[db.ACCESS_SERVER],
                    ),
                    callback_data=cb("server", "", "0"),
                ),
            ]
        )
    return text, InlineKeyboardMarkup(rows)


def _list_rows(playlists: list[dict], show_owner: bool = False) -> list[list[InlineKeyboardButton]]:
    rows = []
    for pl in playlists:
        glyph = MODE_GLYPH.get(pl.get("access_mode"), "")
        count = pl.get("song_count", 0)
        title = pl.get("title", "Untitled")
        # Telegram truncates long button labels mid-glyph; clip ourselves so the
        # song count stays readable.
        if len(title) > 24:
            title = title[:23] + "…"
        label = f"{glyph} {title} · {count}"
        rows.append([InlineKeyboardButton(label, callback_data=cb("view", pl["playlist_id"]))])
    return rows


def render_library(
    playlists: list[dict], page: int, total: int
) -> tuple[str, InlineKeyboardMarkup]:
    total_pages = _total_pages(total, PAGE_SIZE)

    if not playlists:
        text = tr(
            "playlist.ui.library_don_t_have_any_playlists_yet_tap",
            g_library=G_LIBRARY,
            g_add=G_ADD,
            g_fork=G_FORK,
        )
    else:
        text = tr(
            "playlist.ui.library_playlist_page",
            g_library=G_LIBRARY,
            total=total,
            playlist="s" if total != 1 else "",
            page=page + 1,
            total_pages=total_pages,
        )

    rows = _list_rows(playlists)
    pager = pager_row("lib", page, total_pages)
    if pager:
        rows.append(pager)
    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.new", g_add=G_ADD),
                callback_data=cb("newprompt"),
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("root")),
        ]
    )
    return text, InlineKeyboardMarkup(rows)


def render_discovery(
    playlists: list[dict],
    page: int,
    kind: str,
    query: str = "",
) -> tuple[str, InlineKeyboardMarkup]:
    if kind == "trend":
        header = f"**{G_TREND} Trending**"
        empty = tr("playlist.ui.nothing_trending_yet_first_tap_new_playlist_add", g_add=G_ADD)
    elif kind == "browse":
        header = tr("playlist.ui.browse_all", g_browse=G_BROWSE)
        empty = tr("playlist.ui.no_public_playlists_yet_make_first_one_tap", g_add=G_ADD)
    elif kind == "search":
        header = tr("playlist.ui.results", g_search=G_SEARCH, query=query)
        empty = tr("playlist.ui.no_public_playlists_matched_try_different_word_tap", g_add=G_ADD)
    elif kind == "server":
        header = tr("playlist.ui.group_playlists", mode_glyph=MODE_GLYPH[db.ACCESS_SERVER])
        empty = tr("playlist.ui.no_group_playlists_yet_create_one_set_its")
    else:
        header = f"**{G_SAVE} Saved**"
        empty = tr(
            "playlist.ui.haven_t_saved_any_playlists_yet_tap_browse",
            g_browse=G_BROWSE,
            g_save=G_SAVE,
        )

    if not playlists:
        text = f"{header}\n\n{empty}"
        rows = [
            [
                InlineKeyboardButton(
                    tr("playlist.ui.new_playlist", g_add=G_ADD),
                    callback_data=cb("newprompt"),
                    style=ButtonStyle.SUCCESS,
                ),
            ],
            [InlineKeyboardButton(tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("root"))],
        ]
        return text, InlineKeyboardMarkup(rows)

    lines = [header, ""]
    for i, pl in enumerate(playlists, start=page * PAGE_SIZE + 1):
        glyph = MODE_GLYPH.get(pl.get("access_mode"), "")
        lines.append(
            tr(
                "playlist.ui.songs_plays",
                position=i,
                glyph=glyph,
                title=pl.get("title", "Untitled"),
                song_count=pl.get("song_count", 0),
                plays=pl.get("plays", 0),
                likes=pl.get("likes", 0),
                g_like=G_LIKE,
            )
        )

    rows = _list_rows(playlists, show_owner=True)

    has_next = len(playlists) >= PAGE_SIZE
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(G_PREV, callback_data=cb(kind, "", f"{page - 1}|{query}")))
    nav.append(InlineKeyboardButton(tr("admin.dare_dare", dare=page + 1), callback_data=NOOP))
    if has_next:
        nav.append(InlineKeyboardButton(G_NEXT, callback_data=cb(kind, "", f"{page + 1}|{query}")))
    if len(nav) > 1:
        rows.append(nav)

    rows.append(
        [InlineKeyboardButton(tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("root"))]
    )
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def render_playlist_view(
    pl: dict,
    user_id: int,
    client: Client | None = None,
    page: int = 0,
) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    is_owner = pl.get("owner_id") == user_id
    can_edit = is_owner or user_id in pl.get("editors", [])

    songs, liked, saved = await asyncio.gather(
        db.get_songs(pid, skip=page * SONG_PAGE_SIZE, limit=SONG_PAGE_SIZE),
        db.has_edge(pid, user_id, "like"),
        db.has_edge(pid, user_id, "save"),
    )

    caption = build_playlist_caption(pl)

    if songs:
        lines = [caption, "", "**Tracks**"]
        for s in songs:
            lines.append(
                f"`{s.get('position', 0):>3}.` {s.get('title', 'Unknown')} "
                f"`({format_duration(s.get('duration', 0))})`"
            )
        text = "\n".join(lines)
    else:
        text = caption + tr("playlist.ui.playlist_empty_render_playlist_view")

    total_pages = _total_pages(pl.get("song_count", 0), SONG_PAGE_SIZE)

    rows: list[list[InlineKeyboardButton]] = []

    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.play", g_play=G_PLAY),
                callback_data=cb("play", pid),
                style=ButtonStyle.SUCCESS,
            ),
            InlineKeyboardButton(
                tr("playlist.ui.queue", g_queue=G_QUEUE), callback_data=cb("enqueue", pid)
            ),
        ]
    )

    rows.append(
        [
            InlineKeyboardButton(
                tr(
                    "playlist.ui.render_playlist_view_g_liked_likes",
                    g_liked=G_LIKED if liked else G_LIKE,
                    likes=pl.get("likes", 0),
                ),
                callback_data=cb("like", pid),
            ),
            InlineKeyboardButton(
                tr(
                    "playlist.ui.render_playlist_view_g_liked_likes",
                    g_liked=G_SAVE,
                    likes="Saved" if saved else "Save",
                ),
                callback_data=cb("save", pid),
            ),
            InlineKeyboardButton(
                tr("playlist.ui.copy", g_fork=G_FORK), callback_data=cb("fork", pid)
            ),
        ]
    )

    pager = pager_row("view", page, total_pages, pid)
    if pager:
        rows.append(pager)

    if can_edit:
        rows.append(
            [
                InlineKeyboardButton(
                    tr("playlist.ui.add", g_add=G_ADD), callback_data=cb("addprompt", pid)
                ),
                InlineKeyboardButton(
                    tr("playlist.ui.manage", g_edit=G_EDIT), callback_data=cb("manage", pid)
                ),
            ]
        )

    # Share stays visible for everyone, it's the whole point of a social playlist
    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.share", g_share=G_SHARE), callback_data=cb("share", pid)
            ),
            InlineKeyboardButton(
                tr("playlist.ui.more", g_more=G_MORE), callback_data=cb("more", pid)
            ),
        ]
    )
    rows.append(
        [InlineKeyboardButton(tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("root"))]
    )

    return text, InlineKeyboardMarkup(rows)


def render_more(pl: dict, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    is_owner = pl.get("owner_id") == user_id

    text = tr(
        "playlist.ui.more_stats_plays_likes_completion_activity_who_changed",
        g_more=G_MORE,
        title=pl.get("title", "Untitled"),
        g_stats=G_STATS,
        g_feed=G_FEED,
        g_lineage=G_LINEAGE,
        g_export=G_EXPORT,
        g_qr=G_QR,
    )

    rows = [
        [
            InlineKeyboardButton(
                tr("playlist.ui.stats", g_stats=G_STATS), callback_data=cb("stats", pid)
            ),
            InlineKeyboardButton(
                tr("playlist.ui.activity", g_feed=G_FEED), callback_data=cb("feed", pid)
            ),
        ],
        [
            InlineKeyboardButton(
                tr("playlist.ui.lineage", g_lineage=G_LINEAGE), callback_data=cb("lineage", pid)
            ),
            InlineKeyboardButton(
                tr("playlist.ui.export", g_export=G_EXPORT), callback_data=cb("export", pid)
            ),
        ],
        [
            InlineKeyboardButton(tr("playlist.ui.qr_code", g_qr=G_QR), callback_data=cb("qr", pid)),
        ],
    ]

    if not is_owner:
        rows.append(
            [
                InlineKeyboardButton(
                    tr("playlist.ui.report", g_report=G_REPORT),
                    callback_data=cb("report", pid),
                    style=ButtonStyle.DANGER,
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("view", pid, "0")
            )
        ]
    )
    return text, InlineKeyboardMarkup(rows)


def render_manage(pl: dict, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    is_owner = pl.get("owner_id") == user_id
    mode = pl.get("access_mode")

    editors = pl.get("editors", [])
    text = tr(
        "playlist.ui.manage_access_editors_songs",
        g_edit=G_EDIT,
        title=pl.get("title", "Untitled"),
        mode=MODE_GLYPH.get(mode, ""),
        mode_2=MODE_LABEL.get(mode, "Private"),
        editors=len(editors),
        song_count=pl.get("song_count", 0),
    )

    rows = [
        [
            InlineKeyboardButton(
                tr("playlist.ui.rename", g_edit=G_EDIT), callback_data=cb("rename", pid)
            ),
            InlineKeyboardButton(
                tr("playlist.ui.description", g_edit=G_EDIT), callback_data=cb("redesc", pid)
            ),
        ],
        [
            InlineKeyboardButton(
                tr("playlist.ui.reorder", g_queue=G_QUEUE),
                callback_data=cb("reorder", pid, "0"),
            ),
            InlineKeyboardButton(
                tr("playlist.ui.remove_song", g_delete=G_DELETE),
                callback_data=cb("rmsong", pid, "0"),
            ),
        ],
    ]

    if is_owner:
        rows.append(
            [
                InlineKeyboardButton(
                    tr("playlist.ui.access", mode=MODE_GLYPH.get(mode, "")),
                    callback_data=cb("access", pid),
                ),
                InlineKeyboardButton(
                    tr("playlist.ui.editors", g_add=G_ADD), callback_data=cb("editors", pid)
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    tr("playlist.ui.delete_playlist", g_delete=G_DELETE),
                    callback_data=cb("delprompt", pid),
                    style=ButtonStyle.DANGER,
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("view", pid, "0")
            )
        ]
    )
    return text, InlineKeyboardMarkup(rows)


def render_access(pl: dict) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    current = pl.get("access_mode")

    text = tr(
        "playlist.ui.access_private_only_editors_unlisted_anyone_link_public",
        title=pl.get("title", "Untitled"),
        mode_glyph=MODE_GLYPH[db.ACCESS_PRIVATE],
        mode_glyph_2=MODE_GLYPH[db.ACCESS_UNLISTED],
        mode_glyph_3=MODE_GLYPH[db.ACCESS_PUBLIC],
        mode_glyph_4=MODE_GLYPH[db.ACCESS_SERVER],
        mode_glyph_5=MODE_GLYPH[db.ACCESS_COLLAB],
    )

    rows = []
    for mode in db.ACCESS_MODES:
        marker = "•" if mode == current else " "
        rows.append(
            [
                InlineKeyboardButton(
                    tr(
                        "playlist.ui.render_access_marker_mode_glyph_mode_label",
                        marker=marker,
                        mode_glyph=MODE_GLYPH[mode],
                        mode_label=MODE_LABEL[mode],
                    ),
                    callback_data=cb("setaccess", pid, mode),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("manage", pid)
            )
        ]
    )
    return text, InlineKeyboardMarkup(rows)


def render_duplicate_prompt(
    pl: dict, existing: dict, new_track: dict, token: str
) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    text = tr(
        "playlist.ui.already_playlist_existing_position_new_replace_stored_copy",
        title=existing.get("title", "Unknown"),
        duration=format_duration(existing.get("duration", 0)),
        position=existing.get("position", 0),
        title_2=new_track.get("title", "Unknown"),
        duration_2=format_duration(new_track.get("duration", 0)),
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("playlist.ui.replace"),
                    callback_data=cb("dupreplace", pid, token),
                    style=ButtonStyle.PRIMARY,
                ),
                InlineKeyboardButton(
                    tr("playlist.ui.skip"),
                    callback_data=cb("dupskip", pid, token),
                    style=ButtonStyle.DEFAULT,
                ),
            ]
        ]
    )
    return text, markup


def render_delete_confirm(pl: dict) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    text = tr(
        "playlist.ui.delete_removes_playlist_all_its_songs_forks_other",
        g_delete=G_DELETE,
        title=pl.get("title", "Untitled"),
        song_count=pl.get("song_count", 0),
    )
    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("playlist.ui.delete", g_delete=G_DELETE),
                    callback_data=cb("delete", pid),
                    style=ButtonStyle.DANGER,
                ),
                InlineKeyboardButton(tr("buttons.cancel"), callback_data=cb("manage", pid)),
            ]
        ]
    )
    return text, markup


def render_share(pl: dict, link: str) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    mode = pl.get("access_mode")

    note = ""
    if mode == db.ACCESS_PRIVATE:
        note = tr(
            "playlist.ui.playlist_private_link_only_works_its_editors_switch",
            mode_glyph=MODE_GLYPH[db.ACCESS_PRIVATE],
        )
    elif mode == db.ACCESS_SERVER:
        note = tr(
            "playlist.ui.playlist_server_only_link_only_works_members_its",
            mode_glyph=MODE_GLYPH[db.ACCESS_SERVER],
        )

    text = tr(
        "playlist.ui.share_id",
        g_share=G_SHARE,
        title=pl.get("title", "Untitled"),
        link=link,
        pid=pid,
        note=note,
    )
    rows = [
        [InlineKeyboardButton(tr("playlist.ui.open_link", g_share=G_SHARE), url=link)],
    ]
    if mode in (db.ACCESS_PRIVATE, db.ACCESS_SERVER):
        rows.append(
            [
                InlineKeyboardButton(
                    tr("playlist.ui.change_access", g_edit=G_EDIT),
                    callback_data=cb("access", pid),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(tr("playlist.ui.qr_code", g_qr=G_QR), callback_data=cb("qr", pid)),
            InlineKeyboardButton(
                tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("view", pid, "0")
            ),
        ]
    )
    return text, InlineKeyboardMarkup(rows)


def back_row(pid: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("more", pid))
    ]


def simple_view(text: str, pid: str) -> tuple[str, InlineKeyboardMarkup]:
    return text, InlineKeyboardMarkup([back_row(pid)])


def render_prompt(text: str, pid: str) -> tuple[str, InlineKeyboardMarkup]:
    back = cb("view", pid, "0") if pid else cb("root")
    return text, InlineKeyboardMarkup(
        [[InlineKeyboardButton(tr("playlist.ui.cancel", g_back=G_BACK), callback_data=back)]]
    )


def render_pm_handoff(prompt_text: str) -> tuple[str, InlineKeyboardMarkup]:
    text = tr("playlist.ui.can_only_read_reply_private_chat", prompt_text=prompt_text)
    return text, InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    tr("playlist.ui.continue_pm", g_share=G_SHARE),
                    url=f"https://t.me/{bot_username()}",
                )
            ]
        ]
    )


def render_song_picker(
    pl: dict, songs: list[dict], page: int, mode: str
) -> tuple[str, InlineKeyboardMarkup]:
    title = pl.get("title", "Untitled")
    glyph, heading, hint, prefix = _PICKER_MODES[mode]

    if not songs:
        return (
            tr("playlist.ui.playlist_empty", glyph=glyph, heading=heading, title=title),
            InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            tr("playlist.ui.back", g_back=G_BACK),
                            callback_data=cb("manage", pl["playlist_id"]),
                        )
                    ]
                ]
            ),
        )

    pid = pl["playlist_id"]
    rows = [
        [
            InlineKeyboardButton(
                tr(
                    "playlist.ui.render_song_picker_glyph_position_title",
                    glyph=glyph,
                    position=s.get("position"),
                    title=(s.get("title") or "")[:28],
                ),
                callback_data=cb(mode, pid, f"{prefix}{s.get('position')}"),
            )
        ]
        for s in songs
    ]

    pager = pager_row(mode, page, _total_pages(pl.get("song_count", 0), SONG_PAGE_SIZE), pid)
    if pager:
        rows.append(pager)
    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("manage", pid)
            )
        ]
    )

    return f"**{glyph} {heading} — {title}**\n\n{hint}", InlineKeyboardMarkup(rows)


# mode -> (glyph, heading, hint, callback arg prefix)
_PICKER_MODES = {
    "rmsong": (G_DELETE, "Remove", tr("playlist.ui.tap_track_remove"), "p"),
    "reorder": (G_QUEUE, "Reorder", tr("playlist.ui.tap_track_move_one_place_earlier"), "u"),
}


def render_editors(pl: dict, names: dict[int, str]) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    editors = pl.get("editors", []) or []

    if editors:
        blurb = tr("playlist.ui.editors_can_add_remove_songs_only_can_delete")
    else:
        blurb = tr("playlist.ui.no_editors_yet_add_one_make_playlist_collaborative")

    text = f"**{G_ADD} Editors — {pl.get('title', 'Untitled')}**\n\n{blurb}"

    rows = [
        [
            InlineKeyboardButton(
                tr(
                    "playlist.ui.render_playlist_view_g_liked_likes",
                    g_liked=G_DELETE,
                    likes=names.get(uid, str(uid)),
                ),
                callback_data=cb("editors", pid, f"r{uid}"),
            )
        ]
        for uid in editors
    ]
    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.add_editor", g_add=G_ADD), callback_data=cb("addeditor", pid)
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                tr("playlist.ui.back", g_back=G_BACK), callback_data=cb("manage", pid)
            )
        ]
    )
    return text, InlineKeyboardMarkup(rows)


def render_export_picker(pl: dict) -> tuple[str, InlineKeyboardMarkup]:
    pid = pl["playlist_id"]
    text = tr(
        "playlist.ui.export_json_full_metadata_re_importable_m3u_opens",
        g_export=G_EXPORT,
        title=pl.get("title", "Untitled"),
    )
    rows = [
        [
            InlineKeyboardButton(fmt.upper(), callback_data=cb("export", pid, fmt))
            for fmt in EXPORT_FORMATS
        ],
        back_row(pid),
    ]
    return text, InlineKeyboardMarkup(rows)
