import re
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from selectolax.lexbor import LexborHTMLParser

from Emilia.application import db
from Emilia.config import Config
from Emilia.locales import tr
from Emilia.utils.anime import (
    cflag,
    day_,
    make_it_rw,
    pos_no,
    return_json_senpai,
    season_,
)
from Emilia.utils.cache import SimpleCache
from Emilia.utils.client_context import bot_username
from Emilia.utils.executors import run_in_thread
from Emilia.utils.http import get
from Emilia.utils.query_cache import QueryCache
from Emilia.utils.translate import translate_text

ANIME_DB = QueryCache()
MANGA_DB = QueryCache()
CHAR_DB = QueryCache()
STUDIO_DB = QueryCache()
AIRING_DB = QueryCache()
FILLER_CACHE = SimpleCache(3600, "anime_fillers", max_l1_entries=256)
GUI = db["GROUP_UI"]


async def uidata(id_):
    data = await GUI.find_one({"_id": str(id_)})
    if data is not None:
        bullet = str(data["bl"]) + " "
        if data["bl"] is None:
            bullet = ""
        return bullet, data["cs"]
    return ["➤ ", "UPPER"]


def get_ui_text(case):
    if case == "UPPER":
        return [
            "SOURCE",
            "TYPE",
            "SCORE",
            "DURATION",
            tr("anime.user_data"),
            tr("anime.adult_rated"),
            "STATUS",
            "GENRES",
            "TAGS",
            "SEQUEL",
            "PREQUEL",
            tr("anime.next_airing_get_ui_text"),
            "DESCRIPTION",
            "VOLUMES",
            "CHAPTERS",
        ]
    else:
        return [
            "Source",
            "Type",
            "Score",
            "Duration",
            tr("anime.user_data_get_ui_text"),
            tr("anime.adult_rated_get_ui_text"),
            "Status",
            "Genres",
            "Tags",
            "Sequel",
            "Prequel",
            tr("anime.next_airing"),
            "Description",
            "Volumes",
            "Chapters",
        ]


#### Anilist part ####

ANIME_TEMPLATE = tr("anime.id_mal_id_official_site")


# GraphQL Queries.
ANIME_QUERY = """
query ($id: Int, $idMal:Int, $search: String) {
    Media (id: $id, idMal: $idMal, search: $search, type: ANIME) {
        id
        idMal
        title {
            romaji
            english
            native
        }
        format
        status
        episodes
        duration
        countryOfOrigin
        source (version: 2)
        trailer {
            id
            site
        }
        genres
        tags {
            name
        }
        averageScore
        relations {
            edges {
                node {
                    title {
                        romaji
                        english
                    }
                    id
                    type
                }
                relationType
            }
        }
        nextAiringEpisode {
            timeUntilAiring
            episode
        }
        isAdult
        isFavourite
        mediaListEntry {
            status
            score
            id
        }
        siteUrl
    }
}
"""

ISADULT = """
query ($id: Int) {
    Media (id: $id) {
        isAdult
    }
}
"""

BROWSE_QUERY = """
query ($s: MediaSeason, $y: Int, $sort: [MediaSort]) {
    Page {
        media (season: $s, seasonYear: $y, sort: $sort) {
    	    title {
                romaji
            }
            format
        }
    }
}
"""

FAV_ANI_QUERY = """
query ($id: Int, $page: Int) {
    User (id: $id) {
        favourites {
            anime (page: $page, perPage: 10) {
                pageInfo {
                    lastPage
                    hasNextPage
                }
                edges {
                    node {
                        title {
                            romaji
                        }
                        siteUrl
                    }
                }
            }
        }
    }
}
"""

FAV_MANGA_QUERY = """
query ($id: Int, $page: Int) {
    User (id: $id) {
        favourites {
            manga (page: $page, perPage: 10) {
                pageInfo {
                    lastPage
                    hasNextPage
                }
                edges {
                    node {
                        title {
                            romaji
                        }
                        siteUrl
                    }
                }
            }
        }
    }
}
"""

FAV_CHAR_QUERY = """
query ($id: Int, $page: Int) {
    User (id: $id) {
        favourites {
            characters (page: $page, perPage: 10) {
                pageInfo {
                    lastPage
                    hasNextPage
                }
                edges {
                    node {
                        name {
                            full
                        }
                        siteUrl
                    }
                }
            }
        }
    }
}
"""

VIEWER_QRY = """
query {
    Viewer {
        id
        name
        siteUrl
        statistics {
            anime {
                count
                minutesWatched
                episodesWatched
                meanScore
            }
            manga {
                count
                chaptersRead
                volumesRead
                meanScore
            }
        }
    }
}
"""

USER_QRY = """
query ($search: String) {
    User (name: $search) {
        id
        name
        siteUrl
        statistics {
            anime {
                count
                minutesWatched
                episodesWatched
                meanScore
            }
            manga {
                count
                chaptersRead
                volumesRead
                meanScore
            }
        }
    }
}
"""

ANIME_MUTATION = """
mutation ($id: Int) {
    ToggleFavourite (animeId: $id) {
        anime {
            pageInfo {
                total
            }
        }
    }
}
"""

MANGA_MUTATION = """
mutation ($id: Int) {
    ToggleFavourite (mangaId: $id) {
        manga {
            pageInfo {
                total
            }
        }
    }
}
"""

STUDIO_MUTATION = """
mutation ($id: Int) {
    ToggleFavourite (studioId: $id) {
        studios {
            pageInfo {
                total
            }
        }
    }
}
"""

CHAR_MUTATION = """
mutation ($id: Int) {
    ToggleFavourite (characterId: $id) {
        characters {
            pageInfo {
                total
            }
        }
    }
}
"""

ANILIST_MUTATION = """
mutation ($id: Int, $status: MediaListStatus) {
    SaveMediaListEntry (mediaId: $id, status: $status) {
        media {
            title {
                romaji
            }
        }
    }
}
"""

ANILIST_MUTATION_UP = """
mutation ($id: [Int], $status: MediaListStatus) {
    UpdateMediaListEntries (ids: $id, status: $status) {
        media {
            title {
                romaji
            }
        }
    }
}
"""

ANILIST_MUTATION_DEL = """
mutation ($id: Int) {
    DeleteMediaListEntry (id: $id) {
        deleted
    }
}
"""

AIR_QUERY = """
query ($search: String, $page: Int) {
    Page (perPage: 1, page: $page) {
        pageInfo {
            total
            hasNextPage
        }
        media (search: $search, type: ANIME) {
            id
            title {
                romaji
                english
            }
            status
            countryOfOrigin
            nextAiringEpisode {
                timeUntilAiring
                episode
            }
            siteUrl
            isFavourite
            isAdult
            mediaListEntry {
                status
                id
            }
        }
    }
}
"""

DES_INFO_QUERY = """
query ($id: Int) {
    Media (id: $id) {
        id
        description (asHtml: false)
    }
}
"""

CHA_INFO_QUERY = """
query ($id: Int, $page: Int) {
    Media (id: $id, type: ANIME) {
        id
        characters (page: $page, perPage: 25, sort: ROLE) {
            pageInfo {
                hasNextPage
                lastPage
                total
            }
            edges {
                node {
        	        name {
          	            full
        	        }
                }
                role
            }
        }
    }
}
"""

REL_INFO_QUERY = """
query ($id: Int) {
    Media (id: $id, type: ANIME) {
        id
        relations {
            edges {
                node {
                    title {
                        romaji
                    }
                    type
                }
                relationType
            }
        }
    }
}
"""

PAGE_QUERY = """
query ($search: String, $page: Int) {
    Page (perPage: 1, page: $page) {
        pageInfo {
            total
            hasNextPage
        }
        media (search: $search, type: ANIME) {
            id
            idMal
            title {
                romaji
                english
                native
            }
            format
            status
            episodes
            duration
            countryOfOrigin
            source (version: 2)
            trailer {
                id
                site
            }
            genres
            tags {
                name
            }
            averageScore
            relations {
                edges {
                    node {
                        title {
                            romaji
                            english
                        }
                        type
                    }
                    relationType
                }
            }
            nextAiringEpisode {
                timeUntilAiring
                episode
            }
            isAdult
            isFavourite
            mediaListEntry {
                status
                score
                id
            }
            siteUrl
        }
    }
}
"""

CHARACTER_QUERY = """
query ($id: Int, $search: String, $page: Int) {
    Page (perPage: 1, page: $page) {
        pageInfo {
            total
            hasNextPage
        }
        characters (id: $id, search: $search) {
            id
            name {
                full
                native
            }
            image {
                large
            }
            media (type: ANIME) {
                edges {
                    node {
                        title {
                            romaji
                        }
                        type
                    }
                    voiceActors (language: JAPANESE) {
                        name {
                            full
         	            }
                        siteUrl
                    }
                }
            }
            isFavourite
            siteUrl
        }
    }
}
"""

MANGA_QUERY = """
query ($search: String, $page: Int) {
    Page (perPage: 1, page: $page) {
        pageInfo {
            total
            hasNextPage
        }
        media (search: $search, type: MANGA) {
            id
            title {
                romaji
                english
                native
            }
            format
            countryOfOrigin
            source (version: 2)
            status
            description(asHtml: true)
            chapters
            isFavourite
            mediaListEntry {
                status
                score
                id
            }
            volumes
            averageScore
            siteUrl
            isAdult
        }
    }
}
"""


DESC_INFO_QUERY = """
query ($id: Int) {
    Character (id: $id) {
        image {
            large
        }
        description(asHtml: false)
    }
}
"""

LS_INFO_QUERY = """
query ($id: Int) {
    Character (id: $id) {
        image {
            large
        }
        media (page: 1, perPage: 25) {
            nodes {
                title {
                    romaji
                    english
                }
                type
            }
        }
    }
}
"""

ACTIVITY_QUERY = """
query ($id: Int) {
    Page (perPage: 12) {
  	    activities (userId: $id, type: MEDIA_LIST, sort: ID_DESC) {
			...kek
  	    }
    }
}
fragment kek on ListActivity {
    type
    media {
        title {
            romaji
        }
        siteUrl
    }
    progress
    status
}
"""

TOP_QUERY = """
query ($gnr: String, $page: Int) {
    Page (perPage: 15, page: $page) {
        pageInfo {
            lastPage
            total
            hasNextPage
        }
        media (genre: $gnr, sort: SCORE_DESC, type: ANIME) {
            title {
                romaji
            }
        }
    }
}
"""

TOPT_QUERY = """
query ($gnr: String, $page: Int) {
    Page (perPage: 15, page: $page) {
        pageInfo {
            lastPage
            total
            hasNextPage
        }
        media (tag: $gnr, sort: SCORE_DESC, type: ANIME) {
            title {
                romaji
            }
        }
    }
}
"""

ALLTOP_QUERY = """
query ($page: Int) {
    Page (perPage: 15, page: $page) {
        pageInfo {
            lastPage
            total
            hasNextPage
        }
        media (sort: SCORE_DESC, type: ANIME) {
            title {
                romaji
            }
        }
    }
}
"""

GET_GENRES = """
query {
    GenreCollection
}
"""

GET_TAGS = """
query{
    MediaTagCollection {
        name
        isAdult
    }
}
"""

RECOMMENDTIONS_QUERY = """
query ($id: Int) {
    Media (id: $id) {
        recommendations (perPage: 25) {
            edges {
                node {
                    mediaRecommendation {
                        title {
                            romaji
                        }
                        id
                        siteUrl
                    }
                }
            }
        }
    }
}
"""

STUDIO_QUERY = """
query ($search: String, $page: Int) {
    Page (page: $page, perPage: 1) {
        pageInfo {
            total
            hasNextPage
        }
  	    studios (search: $search) {
    	    id
    	    name
  	        siteUrl
            isFavourite
  	    }
	}
}
"""

STUDIO_ANI_QUERY = """
query ($id: Int, $page: Int) {
    Studio (id: $id) {
        name
        media (page: $page) {
            pageInfo {
                total
                lastPage
                hasNextPage
            }
            edges {
                node  {
                    title {
                        romaji
                    }
                    seasonYear
                }
            }
        }
    }
}
"""


async def get_studios(qry, page, user, duser=None, auth: bool = False):
    page = int(page)
    vars_ = {"search": STUDIO_DB[qry], "page": int(page)}
    result = await return_json_senpai(STUDIO_QUERY, vars_, auth, user)
    if result["data"]["Page"]["studios"] == []:
        return AnimeError(tr("anime.not_found"))
    data = result["data"]["Page"]["studios"][0]
    isFav = data["isFavourite"]
    msg = f"**{data['name']}**{', ♥️' if isFav is True else ''}" + tr(
        "anime.id_website", studio_id=data["id"], url=data["siteUrl"]
    )
    if not duser:
        duser = user
    btns = []
    btns.append(
        [
            InlineKeyboardButton(
                tr("anime.list_animes"),
                callback_data=f"stuani_1_{data['id']}_{page}_{qry}_{auth}_{duser}",
            )
        ]
    )
    if auth:
        btns.append(
            [
                InlineKeyboardButton(
                    tr("anime.remove_from_favs") if isFav else tr("anime.add_favs"),
                    callback_data=f"fav_STUDIO_{data['id']}_{qry}_{page}_{duser}",
                )
            ]
        )
    pi = result["data"]["Page"]["pageInfo"]["hasNextPage"]
    if pi is False:
        if int(page) == 1:
            return msg, btns
        else:
            btns.append(
                [
                    InlineKeyboardButton(
                        tr("anime.prev"),
                        callback_data=f"pgstudio_{page - 1}_{qry}_{auth}_{duser}",
                    )
                ]
            )
    else:
        if int(page) == 1:
            btns.append(
                [
                    InlineKeyboardButton(
                        tr("buttons.next"),
                        callback_data=f"pgstudio_2_{qry}_{auth}_{duser}",
                    )
                ]
            )
        else:
            btns.append(
                [
                    InlineKeyboardButton(
                        tr("anime.prev"),
                        callback_data=f"pgstudio_{page - 1}_{qry}_{auth}_{duser}",
                    ),
                    InlineKeyboardButton(
                        tr("buttons.next"),
                        callback_data=f"pgstudio_{page + 1}_{qry}_{auth}_{duser}",
                    ),
                ]
            )
    return msg, InlineKeyboardMarkup(btns)


async def get_studio_animes(id_, page, qry, rp, user, duser=None, auth: bool = False):
    vars_ = {"id": id_, "page": int(page)}
    result = await return_json_senpai(STUDIO_ANI_QUERY, vars_, auth, user)
    data = result["data"]["Studio"]["media"]["edges"]
    if data == []:
        return AnimeError(tr("anime.no_results_found_get_studio_animes"))
    msg = tr("anime.list_animes_studio", name=result["data"]["Studio"]["name"])
    for i in data:
        msg += f"\n⚬ `{i['node']['title']['romaji']}`" + f" __({i['node']['seasonYear']})__"
    btns = []
    if not duser:
        duser = user
    pi = result["data"]["Studio"]["media"]["pageInfo"]
    if pi["hasNextPage"] is False:
        if int(page) == 1:
            btns.append(
                [
                    InlineKeyboardButton(
                        tr("buttons.back"),
                        callback_data=f"pgstudio_{rp}_{qry}_{auth}_{duser}",
                    )
                ]
            )
            return msg, btns
        else:
            btns.append(
                [
                    InlineKeyboardButton(
                        tr("anime.prev"),
                        callback_data=f"stuani_{int(page) - 1}_{id_}_{rp}_{qry}_{auth}_{duser}",
                    )
                ]
            )
    else:
        if int(page) == 1:
            btns.append(
                [
                    InlineKeyboardButton(
                        tr("buttons.next"),
                        callback_data=f"stuani_2_{id_}_{rp}_{qry}_{auth}_{duser}",
                    )
                ]
            )
        else:
            btns.append(
                [
                    InlineKeyboardButton(
                        tr("anime.prev"),
                        callback_data=f"stuani_{int(page) - 1}_{id_}_{rp}_{qry}_{auth}_{duser}",
                    ),
                    InlineKeyboardButton(
                        tr("buttons.next"),
                        callback_data=f"stuani_{int(page) + 1}_{id_}_{rp}_{qry}_{auth}_{duser}",
                    ),
                ]
            )
    btns.append(
        [
            InlineKeyboardButton(
                tr("buttons.back"), callback_data=f"pgstudio_{rp}_{qry}_{auth}_{duser}"
            )
        ]
    )
    return msg, InlineKeyboardMarkup(btns)


async def get_all_tags(text: str = None):
    vars_ = {}
    result = await return_json_senpai(GET_TAGS, vars_, auth=False, user=None)
    msg = tr("anime.tags_list")
    kek = []
    for i in result["data"]["MediaTagCollection"]:
        if text is not None and "nsfw" in text:
            if i["isAdult"] is True:
                kek.append(i["name"])
        else:
            if i["isAdult"] is False:
                kek.append(i["name"])
    msg += ", ".join(kek)
    msg += "`"
    return msg


async def get_all_genres():
    vars_ = {}
    result = await return_json_senpai(GET_GENRES, vars_, auth=False)
    msg = tr("anime.genres_list")
    for i in result["data"]["GenreCollection"]:
        msg += f"`{i}`\n"
    return msg


async def get_user_activity(id_, user, duser=None):
    vars_ = {"id": id_}
    result = await return_json_senpai(ACTIVITY_QUERY, vars_, auth=True, user=user)
    data = result["data"]["Page"]["activities"]
    msg = ""
    for i in data:
        try:
            name = f"[{i['media']['title']['romaji']}]" + f"({i['media']['siteUrl']})"
            if i["status"] in ["watched episode", "read chapter"]:
                msg += f"⚬ {str(i['status']).capitalize()} " + f"{i['progress']} of {name}\n"
            else:
                progress = i["progress"]
                of = "of"
                if i["status"] == "dropped":
                    of = "at"
                msg += (
                    f"⚬ {str(i['status']).capitalize()}"
                    + f"{f'{progress} {of} ' if progress is not None else ' '}"
                    + f"{name}\n"
                )
        except KeyError:
            pass
    if duser is None:
        duser = user
    btn = [[InlineKeyboardButton(tr("buttons.back"), callback_data=f"getusrbc_{duser}")]]
    return [
        f"https://img.anili.st/user/{id_}?a={time.time()}",
        msg,
        InlineKeyboardMarkup(btn),
    ]


async def get_recommendations(id_, *, client=None):
    vars_ = {"id": int(id_)}
    result = await return_json_senpai(RECOMMENDTIONS_QUERY, vars_)
    data = result["data"]["Media"]["recommendations"]["edges"]
    rc_ls = []
    for i in data:
        ii = i["node"]["mediaRecommendation"]
        rc_ls.append([ii["title"]["romaji"], ii["id"], ii["siteUrl"]])
    if rc_ls == []:
        return tr("anime.no_recommendations_available_related_given_anime")
    outstr = tr("anime.recommended_animes")
    for i in rc_ls:
        outstr += (
            f"**{i[0]}**\n ➥[Synopsis]"
            + f"(https://t.me/{bot_username(client)}?start=anime_{i[1]})"
            + tr("anime.official_site", official_site=i[2])
        )
    return outstr


async def get_top_animes(gnr: str, page, user):
    vars_ = {"gnr": gnr.lower(), "page": int(page)}
    query = TOP_QUERY
    msg = tr("anime.top_animes_genre", gnr=gnr.capitalize())
    if gnr == "None":
        query = ALLTOP_QUERY
        vars_ = {"page": int(page)}
        msg = tr("anime.top_animes")
    nsfw = False
    result = await return_json_senpai(query, vars_, auth=False, user=user)
    if len(result["data"]["Page"]["media"]) == 0:
        query = TOPT_QUERY
        msg = tr("anime.top_animes_tag", gnr=gnr.capitalize())
        result = await return_json_senpai(query, vars_, auth=False, user=user)
        if len(result["data"]["Page"]["media"]) == 0:
            return AnimeError(tr("anime.no_results_found_get_anilist"))
        nsls = await get_all_tags("nsfw")
        nsfw = True if gnr.lower() in nsls.lower() else False
    data = result["data"]["Page"]
    for i in data["media"]:
        msg += f"⚬ `{i['title']['romaji']}`\n"
    msg += tr("anime.total_available_animes", total=data["pageInfo"]["total"])
    btn = []
    if int(page) == 1:
        if int(data["pageInfo"]["lastPage"]) != 1:
            btn.append(
                [
                    InlineKeyboardButton(
                        tr("buttons.next"),
                        callback_data=f"topanimu_{gnr}_{int(page) + 1}_{user}",
                    )
                ]
            )
    elif int(page) == int(data["pageInfo"]["lastPage"]):
        btn.append(
            [
                InlineKeyboardButton(
                    tr("anime.prev"),
                    callback_data=f"topanimu_{gnr}_{int(page) - 1}_{user}",
                )
            ]
        )
    else:
        btn.append(
            [
                InlineKeyboardButton(
                    tr("anime.prev"),
                    callback_data=f"topanimu_{gnr}_{int(page) - 1}_{user}",
                ),
                InlineKeyboardButton(
                    tr("buttons.next"),
                    callback_data=f"topanimu_{gnr}_{int(page) + 1}_{user}",
                ),
            ]
        )
    return [msg, nsfw], InlineKeyboardMarkup(btn) if len(btn) != 0 else ""


async def get_user_favourites(id_, user, req, page, sighs, duser=None):
    vars_ = {"id": int(id_), "page": int(page)}
    result = await return_json_senpai(
        (FAV_ANI_QUERY if req == "ANIME" else FAV_CHAR_QUERY if req == "CHAR" else FAV_MANGA_QUERY),
        vars_,
        auth=True,
        user=int(user),
    )
    data = result["data"]["User"]["favourites"][
        "anime" if req == "ANIME" else "characters" if req == "CHAR" else "manga"
    ]
    msg = (
        tr("anime.favourite_animes")
        if req == "ANIME"
        else tr("anime.favourite_characters")
        if req == "CHAR"
        else tr("anime.favourite_manga")
    )
    for i in data["edges"]:
        node_name = i["node"]["title"]["romaji"] if req != "CHAR" else i["node"]["name"]["full"]
        msg += f"⚬ [{node_name}]({i['node']['siteUrl']})\n"
    btn = []
    if duser is None:
        duser = user
    if int(page) == 1:
        if int(data["pageInfo"]["lastPage"]) != 1:
            btn.append(
                [
                    InlineKeyboardButton(
                        tr("buttons.next"),
                        callback_data=(
                            f"myfavqry_{req}_{id_}_{str(int(page) + 1)}" + f"_{sighs}_{duser}"
                        ),
                    )
                ]
            )
    elif int(page) == int(data["pageInfo"]["lastPage"]):
        btn.append(
            [
                InlineKeyboardButton(
                    tr("anime.prev"),
                    callback_data=(f"myfavqry_{req}_{id_}_{str(int(page) - 1)}_{sighs}_{duser}"),
                )
            ]
        )
    else:
        btn.append(
            [
                InlineKeyboardButton(
                    tr("anime.prev"),
                    callback_data=(f"myfavqry_{req}_{id_}_{str(int(page) - 1)}_{sighs}_{duser}"),
                ),
                InlineKeyboardButton(
                    tr("buttons.next"),
                    callback_data=(f"myfavqry_{req}_{id_}_{str(int(page) + 1)}_{sighs}_{duser}"),
                ),
            ]
        )
    btn.append(
        [InlineKeyboardButton(tr("buttons.back"), callback_data=f"myfavs_{id_}_{sighs}_{user}")]
    )
    return [
        f"https://img.anili.st/user/{id_}?a=({time.time()})",
        msg,
        InlineKeyboardMarkup(btn),
    ]


async def get_featured_in_lists(idm, req, auth: bool = False, user: int = None, page: int = 0):
    vars_ = {"id": int(idm)}
    result = await return_json_senpai(LS_INFO_QUERY, vars_, auth=auth, user=user)
    data = result["data"]["Character"]["media"]["nodes"]
    if req == "ANI":
        out = "ANIMES:\n\n"
        out_ = []
        for ani in data:
            k = ani["title"]["english"] or ani["title"]["romaji"]
            kk = ani["type"]
            if kk == "ANIME":
                out_.append(f"• __{k}__\n")
    else:
        out = "MANGAS:\n\n"
        out_ = []
        for ani in data:
            k = ani["title"]["english"] or ani["title"]["romaji"]
            kk = ani["type"]
            if kk == "MANGA":
                out_.append(f"• __{k}__\n")
    total = len(out_)
    for _ in range(15 * page):
        out_.pop(0)
    out_ = "".join(out_[:15])
    return ([out + out_, total] if len(out_) != 0 else False), result["data"]["Character"]["image"][
        "large"
    ]


async def get_additional_info(idm, ctgry, req=None, page: int = 0):
    vars_ = {"id": int(idm)}
    if req == "char":
        vars_["page"] = page
    result = await return_json_senpai(
        (
            (
                DES_INFO_QUERY
                if req == "desc"
                else CHA_INFO_QUERY
                if req == "char"
                else REL_INFO_QUERY
            )
            if ctgry == "ANI"
            else DESC_INFO_QUERY
        ),
        vars_,
    )
    data = result["data"]["Media"] if ctgry == "ANI" else result["data"]["Character"]
    pic = f"https://img.anili.st/media/{idm}"
    if req == "desc":
        synopsis = data.get("description")
        if Config.LANGUAGE:
            synopsis = await translate_text(synopsis, Config.LANGUAGE)
        return (pic if ctgry == "ANI" else data["image"]["large"]), synopsis
    elif req == "char":
        charlist = []
        for char in data["characters"]["edges"]:
            charlist.append(f"• `{char['node']['name']['full']}` ({char['role']})")
        chrctrs = ("\n").join(charlist)
        charls = f"{chrctrs}" if len(charlist) != 0 else ""
        return pic, charls, data["characters"]["pageInfo"]
    else:
        prqlsql = data.get("relations").get("edges")
        ps = ""
        for i in prqlsql:
            ps += (
                f"• {i['node']['title']['romaji']} "
                + f"({i['node']['type']}) `{i['relationType']}`\n"
            )
        return pic, ps


@dataclass(frozen=True)
class AnimeError:
    message: str


def anime_error(result):
    return result.message if isinstance(result, AnimeError) else None


async def get_anime(vars_, auth: bool = False, user: int = None, cid: int = None, *, client=None):
    result = await return_json_senpai(ANIME_QUERY, vars_, auth=auth, user=user)

    error = result.get("errors")
    if error:
        error_sts = error[0].get("message")
        return AnimeError(error_sts)

    data = result["data"]["Media"]

    # Data of all fields in returned json
    # pylint: disable=possibly-unused-variable
    idm = data.get("id")
    idmal = data.get("idMal")
    romaji = data["title"]["romaji"]
    english = data["title"]["english"]
    native = data["title"]["native"]
    formats = data.get("format")
    status = data.get("status")
    episodes = data.get("episodes")
    duration = data.get("duration")
    country = data.get("countryOfOrigin")
    c_flag = cflag(country)
    source = data.get("source")
    prqlsql = data.get("relations").get("edges")
    adult = data.get("isAdult")
    url = data.get("siteUrl")
    trailer_link = "N/A"
    gnrs = ", ".join(data["genres"])
    score = data["averageScore"]
    bl, cs = await uidata(cid)
    text = get_ui_text(cs)
    psrc, ptype = text[0], text[1]
    avscd = f"\n{bl}**{text[2]}:** `{score}%` 🌟" if score is not None else ""
    tags = []
    for i in data["tags"]:
        tags.append(i["name"])
    tags_ = f"\n{bl}**{text[8]}:** `{', '.join(tags[:5])}`" if tags != [] else ""
    bot = bot_username(client)
    gnrs_ = ""
    if len(gnrs) != 0:
        gnrs_ = f"\n{bl}**{text[7]}:** `{gnrs}`"
    isfav = data.get("isFavourite")
    fav = tr("anime.favourites_get_anime") if isfav is True else ""
    user_data = ""
    in_ls = False
    in_ls_id = None
    if auth is True:
        in_list = data.get("mediaListEntry")
        if in_list is not None:
            in_ls = True
            in_ls_id = in_list["id"]
            in_ls_stts = in_list["status"]
            in_ls_score = (
                tr("anime.scored", score=in_list["score"]) if in_list["score"] != 0 else ""
            )
            user_data = f"\n{bl}**{text[4]}:** `{in_ls_stts}{fav}{in_ls_score}`"
    if data["title"]["english"] is not None:
        name = f"""[{c_flag}]**{romaji}**
        __{english}__
        {native}"""
    else:
        name = f"""[{c_flag}]**{romaji}**
        {native}"""
    prql, prql_id, sql, sql_id = "", None, "", None
    for i in prqlsql:
        if i["relationType"] == "PREQUEL" and i["node"]["type"] == "ANIME":
            pname = (
                i["node"]["title"]["english"]
                if i["node"]["title"]["english"] is not None
                else i["node"]["title"]["romaji"]
            )
            prql += f"**{text[10]}:** `{pname}`\n"
            prql_id = i["node"]["id"]
            break
    for i in prqlsql:
        if i["relationType"] == "SEQUEL" and i["node"]["type"] == "ANIME":
            sname = (
                i["node"]["title"]["english"]
                if i["node"]["title"]["english"] is not None
                else i["node"]["title"]["romaji"]
            )
            sql += f"**{text[9]}:** `{sname}`\n"
            sql_id = i["node"]["id"]
            break
    additional = f"{prql}{sql}"
    surl = f"https://t.me/{bot}/?start=des_ANI_{idm}_desc"
    dura = (
        tr("anime.min_ep", icon=bl, label=text[3], minutes=duration) if duration is not None else ""
    )
    air_on = None
    if data["nextAiringEpisode"]:
        nextAir = data["nextAiringEpisode"]["timeUntilAiring"]
        air_on = make_it_rw(nextAir * 1000)
        eps = data["nextAiringEpisode"]["episode"]
        th = pos_no(str(eps))
        air_on += f" | {eps}{th} eps"
    if air_on is None:
        eps_ = f"` | `{episodes} eps" if episodes is not None else ""
        status_air = f"{bl}**{text[6]}:** `{status}{eps_}`"
    else:
        status_air = f"{bl}**{text[6]}:** `{status}`\n{bl}**{text[11]}:** `{air_on}`"
    if data["trailer"] and data["trailer"]["site"] == "youtube":
        trailer_link = tr("anime.trailer", youtu=data["trailer"]["id"])
    title_img = f"https://img.anili.st/media/{idm}"
    try:
        finals_ = ANIME_TEMPLATE.format(**locals())
    except KeyError as kys:
        return AnimeError(str(kys))
    return (
        title_img,
        finals_,
        [idm, in_ls, in_ls_id, isfav, adult],
        prql_id,
        sql_id,
    )


async def get_anilist(
    qdb, page, auth: bool = False, user: int = None, cid: int = None, *, client=None
):
    vars_ = {"search": ANIME_DB[qdb], "page": page}
    result = await return_json_senpai(PAGE_QUERY, vars_, auth=auth, user=user)

    if len(result["data"]["Page"]["media"]) == 0:
        return AnimeError(tr("anime.no_results_found_get_anilist"))

    data = result["data"]["Page"]["media"][0]
    # Data of all fields in returned json
    # pylint: disable=possibly-unused-variable
    idm = data.get("id")
    bot = bot_username(client)
    idmal = data.get("idMal")
    romaji = data["title"]["romaji"]
    english = data["title"]["english"]
    native = data["title"]["native"]
    formats = data.get("format")
    status = data.get("status")
    episodes = data.get("episodes")
    duration = data.get("duration")
    country = data.get("countryOfOrigin")
    c_flag = cflag(country)
    source = data.get("source")
    prqlsql = data.get("relations").get("edges")
    adult = data.get("isAdult")
    trailer_link = "N/A"
    isfav = data.get("isFavourite")
    gnrs = ", ".join(data["genres"])
    gnrs_ = ""
    bl, cs = await uidata(cid)
    text = get_ui_text(cs)
    psrc, ptype = text[0], text[1]
    if len(gnrs) != 0:
        gnrs_ = f"\n{bl}**{text[7]}:** `{gnrs}`"
    fav = tr("anime.favourites_get_anime") if isfav is True else ""
    score = data["averageScore"]
    avscd = f"\n{bl}**{text[2]}:** `{score}%` 🌟" if score is not None else ""
    tags = []
    for i in data["tags"]:
        tags.append(i["name"])
    tags_ = f"\n{bl}**{text[8]}:** `{', '.join(tags[:5])}`" if tags != [] else ""
    in_ls = False
    in_ls_id = None
    user_data = ""
    if auth is True:
        in_list = data.get("mediaListEntry")
        if in_list is not None:
            in_ls = True
            in_ls_id = in_list["id"]
            in_ls_stts = in_list["status"]
            in_ls_score = (
                tr("anime.scored", score=in_list["score"]) if in_list["score"] != 0 else ""
            )
            user_data = f"\n{bl}**{text[4]}:** `{in_ls_stts}{fav}{in_ls_score}`"
    if data["title"]["english"] is not None:
        name = f"[{c_flag}]**{english}** (`{native}`)"
    else:
        name = f"[{c_flag}]**{romaji}** (`{native}`)"
    prql, sql = "", ""
    for i in prqlsql:
        if i["relationType"] == "PREQUEL" and i["node"]["type"] == "ANIME":
            pname = (
                i["node"]["title"]["english"]
                if i["node"]["title"]["english"] is not None
                else i["node"]["title"]["romaji"]
            )
            prql += f"**{text[10]}:** `{pname}`\n"
            break
    for i in prqlsql:
        if i["relationType"] == "SEQUEL" and i["node"]["type"] == "ANIME":
            sname = (
                i["node"]["title"]["english"]
                if i["node"]["title"]["english"] is not None
                else i["node"]["title"]["romaji"]
            )
            sql += f"**{text[9]}:** `{sname}`\n"
            break
    additional = f"{prql}{sql}"
    additional.replace("-", "")
    dura = (
        tr("anime.min_ep", icon=bl, label=text[3], minutes=duration) if duration is not None else ""
    )
    air_on = None
    if data["nextAiringEpisode"]:
        nextAir = data["nextAiringEpisode"]["timeUntilAiring"]
        air_on = make_it_rw(nextAir * 1000)
        eps = data["nextAiringEpisode"]["episode"]
        th = pos_no(str(eps))
        air_on += f" | {eps}{th} eps"
    if air_on is None:
        eps_ = f"` | `{episodes} eps" if episodes is not None else ""
        status_air = f"{bl}**{text[6]}:** `{status}{eps_}`"
    else:
        status_air = f"{bl}**{text[6]}:** `{status}`\n{bl}**{text[11]}:** `{air_on}`"
    if data["trailer"] and data["trailer"]["site"] == "youtube":
        trailer_link = tr("anime.trailer", youtu=data["trailer"]["id"])
    url = data.get("siteUrl")
    title_img = f"https://img.anili.st/media/{idm}"
    surl = f"https://t.me/{bot}/?start=des_ANI_{idm}_desc"
    hasNextPage = result["data"]["Page"]["pageInfo"]["hasNextPage"]
    try:
        finals_ = ANIME_TEMPLATE.format(**locals())
    except KeyError as kys:
        return AnimeError(str(kys))
    return title_img, [finals_, hasNextPage], [idm, in_ls, in_ls_id, isfav, adult]


async def get_character(query, page, auth: bool = False, user: int = None):
    var = {"search": CHAR_DB[query], "page": int(page)}
    result = await return_json_senpai(CHARACTER_QUERY, var, auth=auth, user=user)
    if len(result["data"]["Page"]["characters"]) == 0:
        return AnimeError(tr("anime.no_results_found_get_anilist"))
    data = result["data"]["Page"]["characters"][0]
    # Character Data
    id_ = data["id"]
    name = data["name"]["full"]
    native = data["name"]["native"]
    img = data["image"]["large"]
    site_url = data["siteUrl"]
    isfav = data.get("isFavourite")
    va = []
    for i in data["media"]["edges"]:
        for ii in i["voiceActors"]:
            if f"[{ii['name']['full']}]({ii['siteUrl']})" not in va:
                va.append(f"[{ii['name']['full']}]({ii['siteUrl']})")
    lva = None
    if len(va) > 1:
        lva = va.pop()
    sva = (
        tr("anime.voice_actors", voice_actors=", ".join(va))
        + f"{' and ' + lva if lva is not None else ''}\n"
        if va != []
        else ""
    )
    cap_text = tr(
        "anime.id_visit_website",
        native_name=native,
        name=name,
        character_id=id_,
        voice_actors=sva,
        url=site_url,
    )
    hasNextPage = result["data"]["Page"]["pageInfo"]["hasNextPage"]
    return img, [cap_text, hasNextPage], [id_, isfav]


async def browse_(qry: str):
    s, y = season_()
    sort = "POPULARITY_DESC"
    if qry == "upcoming":
        s, y = season_(True)
    if qry == "trending":
        sort = "TRENDING_DESC"
    vars_ = {"s": s, "y": y, "sort": sort}
    result = await return_json_senpai(BROWSE_QUERY, vars_)
    data = result["data"]["Page"]["media"]
    ls = []
    for i in data:
        if i["format"] in ["TV", "MOVIE", "ONA"]:
            ls.append("• `" + i["title"]["romaji"] + "`")
    out = tr("anime.animes", query=qry.capitalize(), animes=s, animes_2=y)
    return out + "\n".join(ls[:20])


async def get_manga(
    qdb, page, auth: bool = False, user: int = None, cid: int = None, *, client=None
):
    vars_ = {"search": MANGA_DB[qdb], "asHtml": True, "page": page}
    result = await return_json_senpai(MANGA_QUERY, vars_, auth=auth, user=user)
    if len(result["data"]["Page"]["media"]) == 0:
        return AnimeError(tr("anime.no_results_found_get_anilist"))
    data = result["data"]["Page"]["media"][0]

    # Data of all fields in returned json
    # pylint: disable=possibly-unused-variable
    idm = data.get("id")
    romaji = data["title"]["romaji"]
    english = data["title"]["english"]
    native = data["title"]["native"]
    status = data.get("status")
    synopsis = data.get("description")
    description = synopsis[:500]
    description_s = ""
    if len(synopsis) > 500:
        description += "..."
        description_s = (
            tr("anime.click_more_info", client=bot_username(client))
            + f"/?start=des_ANI_{idm}_desc)"
        )
    volumes = data.get("volumes")
    chapters = data.get("chapters")
    score = data.get("averageScore")
    url = data.get("siteUrl")
    format_ = data.get("format")
    country = data.get("countryOfOrigin")
    source = data.get("source")
    c_flag = cflag(country)
    isfav = data.get("isFavourite")
    adult = data.get("isAdult")
    fav = tr("anime.favourites_get_anime") if isfav is True else ""
    in_ls = False
    in_ls_id = None
    bl, cs = await uidata(cid)
    text = get_ui_text(cs)
    user_data = ""
    if auth is True:
        in_list = data.get("mediaListEntry")
        if in_list is not None:
            in_ls = True
            in_ls_id = in_list["id"]
            in_ls_stts = in_list["status"]
            in_ls_score = (
                tr("anime.scored", score=in_list["score"]) if in_list["score"] != 0 else ""
            )
            user_data = f"{bl}**{text[4]}:** `{in_ls_stts}{fav}{in_ls_score}`\n"
    name = f"""[{c_flag}]**{romaji}**
        __{english}__
        {native}"""
    if english is None:
        name = f"""[{c_flag}]**{romaji}**
        {native}"""
    finals_ = f"{name}\n\n"
    finals_ += f"{bl}**ID:** `{idm}`\n"
    finals_ += f"{bl}**{text[6]}:** `{status}`\n"
    finals_ += f"{bl}**{text[13]}:** `{volumes}`\n"
    finals_ += f"{bl}**{text[14]}:** `{chapters}`\n"
    finals_ += f"{bl}**{text[2]}:** `{score}`\n"
    finals_ += f"{bl}**{text[1]}:** `{format_}`\n"
    finals_ += f"{bl}**{text[0]}:** `{source}`\n"
    finals_ += user_data
    if Config.LANGUAGE:
        description = await translate_text(description, Config.LANGUAGE)
    findesc = "" if description == "" else f"`{description}`"
    finals_ += f"\n**{text[12]}**: {findesc}\n\n{description_s}"
    pic = f"https://img.anili.st/media/{idm}"
    return (
        pic,
        [finals_, result["data"]["Page"]["pageInfo"]["hasNextPage"], url],
        [idm, in_ls, in_ls_id, isfav, adult],
    )


async def get_airing(qry, ind: int, auth: bool = False, user: int = None):
    vars_ = {"search": AIRING_DB[qry], "page": int(ind)}
    result = await return_json_senpai(AIR_QUERY, vars_, auth=auth, user=user)
    error = result.get("errors")
    if error:
        error_sts = error[0].get("message")
        return AnimeError(error_sts)
    try:
        data = result["data"]["Page"]["media"][0]
    except IndexError:
        return AnimeError(tr("anime.no_results_found_get_anilist"))
    # Airing Details
    mid = data.get("id")
    romaji = data["title"]["romaji"]
    english = data["title"]["english"]
    status = data.get("status")
    country = data.get("countryOfOrigin")
    c_flag = cflag(country)
    coverImg = f"https://img.anili.st/media/{mid}"
    isfav = data.get("isFavourite")
    adult = data.get("isAdult")
    in_ls = False
    in_ls_id = None
    user_data = ""
    if auth is True:
        in_list = data.get("mediaListEntry")
        if in_list is not None:
            in_ls = True
            in_ls_id = in_list["id"]
            in_ls_stts = in_list["status"]
            user_data = tr("anime.user_data_get_airing", in_ls_stts=in_ls_stts)
    air_on = None
    if data["nextAiringEpisode"]:
        nextAir = data["nextAiringEpisode"]["timeUntilAiring"]
        episode = data["nextAiringEpisode"]["episode"]
        th = pos_no(episode)
        air_on = make_it_rw(nextAir * 1000)
    title_ = english or romaji
    out = f"[{c_flag}] **{title_}**"
    out += f"\n\n**ID:** `{mid}`"
    out += f"\n**Status:** `{status}`\n"
    out += user_data
    if air_on:
        out += tr("anime.airing_episode", episode=episode, airing_episode=th, air_on=air_on)
    site = data["siteUrl"]
    return (
        [coverImg, out],
        [site, result["data"]["Page"]["pageInfo"]["hasNextPage"]],
        [mid, in_ls, in_ls_id, isfav, adult],
    )


async def toggle_favourites(id_: int, media: str, user: int):
    vars_ = {"id": int(id_)}
    query = (
        ANIME_MUTATION
        if media == "ANIME" or media == "AIRING"
        else (
            CHAR_MUTATION
            if media == "CHARACTER"
            else MANGA_MUTATION
            if media == "MANGA"
            else STUDIO_MUTATION
        )
    )
    k = await return_json_senpai(query=query, vars_=vars_, auth=True, user=int(user))
    try:
        k["data"]["ToggleFavourite"]
        return "ok"
    except KeyError:
        return "failed"


async def get_user(vars_, req, user, display_user=None):
    query = USER_QRY if "user" in req else VIEWER_QRY
    k = await return_json_senpai(
        query=query, vars_=vars_, auth=False if "user" in req else True, user=int(user)
    )
    error = k.get("errors")
    if error:
        error_sts = error[0].get("message")
        return AnimeError(error_sts)

    data = k["data"]["User" if "user" in req else "Viewer"]
    anime = data["statistics"]["anime"]
    manga = data["statistics"]["manga"]
    stats = tr(
        "anime.anime_stats_total_anime_watched_total_episode_watched",
        count=anime["count"],
        episodeswatched=anime["episodesWatched"],
        minuteswatched=anime["minutesWatched"],
        meanscore=anime["meanScore"],
        count_2=manga["count"],
        chaptersread=manga["chaptersRead"],
        volumesread=manga["volumesRead"],
        meanscore_2=manga["meanScore"],
    )
    btn = []
    if "user" not in req:
        btn.append(
            [
                InlineKeyboardButton(
                    tr("anime.favourites"),
                    callback_data=f"myfavs_{data['id']}_yes_{display_user}",
                ),
                InlineKeyboardButton(
                    tr("anime.activity"),
                    callback_data=f"myacc_{data['id']}_{display_user}",
                ),
            ]
        )
    btn.append([InlineKeyboardButton(tr("anime.profile"), url=str(data["siteUrl"]))])
    return [
        f"https://img.anili.st/user/{data['id']}?a={time.time()}",
        stats,
        InlineKeyboardMarkup(btn),
    ]


async def update_anilist(id_, req, user, eid: int = None, status: str = None):
    vars_ = {"id": int(id_), "status": status}
    if req == "lsus":
        vars_ = {"id": int(eid), "status": status}
    if req == "dlt":
        vars_ = {"id": int(eid)}
    k = await return_json_senpai(
        query=(
            ANILIST_MUTATION
            if req == "lsas"
            else ANILIST_MUTATION_UP
            if req == "lsus"
            else ANILIST_MUTATION_DEL
        ),
        vars_=vars_,
        auth=True,
        user=int(user),
    )
    try:
        (
            k["data"]["SaveMediaListEntry"]
            if req == "lsas"
            else (
                k["data"]["UpdateMediaListEntries"]
                if req == "lsus"
                else k["data"]["DeleteMediaListEntry"]
            )
        )
        return "ok"
    except KeyError:
        return "failed"


async def check_if_adult(id_):
    vars_ = {"id": int(id_)}
    k = await return_json_senpai(query=ISADULT, vars_=vars_, auth=False)
    return k["data"]["Media"]["isAdult"] is True


####       END        ####

#### Jikanpy part ####


async def get_scheduled(x: int = 9):
    base_url = "https://api.jikan.moe/v4/schedules/"
    day = str(day_(x if x != 9 else datetime.now().weekday())).lower()
    out = tr("anime.scheduled_animes", day=day.capitalize())
    response = await get(base_url + day)
    response.raise_for_status()
    data = response.json()
    sched_ls = data["data"]
    for i in sched_ls:
        try:
            title = i["titles"][0]["title"]
        except IndexError:
            title = i["title"]
        out += f"• `{title}`\n"
    return out, x if x != 9 else datetime.now().weekday()


####     END      ####

#### chiaki part ####


async def get_wols(x: str):
    response = await get("https://chiaki.vercel.app/search2", params={"query": x})
    response.raise_for_status()
    data = response.json()
    ls = []
    for i in data:
        sls = [data[i], i]
        ls.append(sls)
    return ls


async def get_wo(x: int, page: int):
    response = await get("https://chiaki.vercel.app/get2", params={"group_id": x})
    response.raise_for_status()
    data = response.json()
    msg = tr("anime.watch_order_given_query")
    out = []
    for i in data:
        out.append(f"{i['index']}. `{i['name']}`\n")
    total = len(out)
    out_ = "".join(out[50 * page : 50 * (page + 1)])
    return msg + out_, total


####     END     ####

##### Anime Fillers Part #####


def _parse_filler_index(text):
    index = {}
    tree = LexborHTMLParser(text)
    if not tree.css_first(".Group"):
        raise ValueError("The filler index has no show groups")
    for anchor in tree.css(".Group li a[href]"):
        try:
            url = urlsplit(urljoin("https://www.animefillerlist.com", anchor.attributes["href"]))
        except ValueError:
            continue
        match = re.fullmatch(r"/shows/([A-Za-z0-9_-]+)/?", url.path)
        title = " ".join(anchor.text(separator=" ").split())
        if match and title and url.hostname in {"www.animefillerlist.com", "animefillerlist.com"}:
            index[title] = match[1]
    if not index:
        raise ValueError("The filler index contains no shows")
    return index


async def search_filler(query):
    query = query.strip().casefold()
    if not query:
        return {}

    async def load():
        response = await get("https://www.animefillerlist.com/shows", max_bytes=2 * 1024**2)
        response.raise_for_status()
        return await run_in_thread(_parse_filler_index, response.text)

    index = await FILLER_CACHE.get_or_load("index", load)
    return {title: slug for title, slug in index.items() if query in title.casefold()}


def _parse_filler_episodes(text, filler_id):
    result = dict.fromkeys(("total_ep", "mixed_ep", "filler_ep", "ac_ep"))
    result["filler_id"] = filler_id
    condensed = LexborHTMLParser(text).css_first("#Condensed")
    if condensed is None:
        raise ValueError("The filler page has no episode summary")
    fields = {
        "manga_canon": "total_ep",
        "mixed_canon/filler": "mixed_ep",
        "filler": "filler_ep",
        "anime_canon": "ac_ep",
    }
    labels = {
        "manga canon episodes": "total_ep",
        "mixed canon/filler episodes": "mixed_ep",
        "filler episodes": "filler_ep",
        "anime canon episodes": "ac_ep",
    }
    matched = False
    for episodes in condensed.css(".Episodes"):
        classes = (episodes.parent.attributes.get("class") or "").split()
        field = next((fields[name] for name in classes if name in fields), None)
        if field is None and (label := episodes.parent.css_first(".Label")) is not None:
            field = labels.get(" ".join(label.text(separator=" ").split()).rstrip(":").casefold())
        if field:
            matched = True
            values = [anchor.text(strip=True) for anchor in episodes.css("a")]
            result[field] = ", ".join(value for value in values if value) or None
    if not matched:
        raise ValueError("The filler page has no recognized episode categories")
    return result


async def parse_filler(filler_id):
    if not isinstance(filler_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", filler_id):
        raise ValueError("Invalid filler show identifier")

    async def load():
        response = await get(
            "https://www.animefillerlist.com/shows/" + filler_id, max_bytes=2 * 1024**2
        )
        response.raise_for_status()
        return await run_in_thread(_parse_filler_episodes, response.text, filler_id)

    return await FILLER_CACHE.get_or_load(f"show:{filler_id}", load)
