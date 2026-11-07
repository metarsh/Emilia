from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pymongo import IndexModel


@dataclass(frozen=True)
class IndexSpec:
    collection: str
    keys: tuple[tuple[str, int | str], ...]
    name: str
    options: dict[str, Any] = field(default_factory=dict)


INDEXES = (
    IndexSpec("coup", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("chatlevels", (("user_id", 1), ("points", -1)), "user_id_1_points_-1", {}),
    IndexSpec("chatlevels", (("chat_id", 1), ("points", -1)), "chat_id_1_points_-1", {}),
    IndexSpec("chatlevels", (("chat_id", 1), ("user_id", 1)), "uniq_chat_user", {"unique": True}),
    IndexSpec("users", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec("chats", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("locks", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("blocklists", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("notes", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("filters", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("welcome", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("rules", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("warn_settings", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec(
        "admincache",
        (("bot_id", 1), ("chat_id", 1), ("user_id", 1)),
        "uniq_bot_chat_user",
        {"unique": True},
    ),
    IndexSpec(
        "admincache", (("last_updated", 1),), "last_updated_1", {"expireAfterSeconds": 86400}
    ),
    IndexSpec(
        "user_warnings",
        (("chat_id", 1), ("user_id", 1), ("warn_id", 1)),
        "uniq_warn_triplet",
        {"unique": True},
    ),
    IndexSpec("afk", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec("nsfw", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("pin", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("reports", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("disable", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("connection", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec("user_info", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec("nightmode", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec(
        "feds",
        (("fed_id", 1),),
        "fed_id_1",
        {"unique": True, "partialFilterExpression": {"fed_id": {"$type": "string"}}},
    ),
    IndexSpec(
        "feds",
        (("owner_id", 1),),
        "owner_id_1",
        {"unique": True, "partialFilterExpression": {"owner_id": {"$type": "number"}}},
    ),
    IndexSpec(
        "feds",
        (("chats", 1),),
        "chats_1",
        {"unique": True, "partialFilterExpression": {"chats.0": {"$exists": True}}},
    ),
    IndexSpec("feds", (("fedadmins", 1),), "fedadmins_1", {}),
    IndexSpec("fbans", (("fed_id", 1),), "fed_id_1", {"unique": True}),
    IndexSpec("fsubs", (("fed_id", 1),), "fed_id_1", {"unique": True}),
    IndexSpec("fsubs", (("my_subs", 1),), "my_subs_1"),
    IndexSpec(
        "federation_mutations", (("expires_at", 1),), "expires_at_1", {"expireAfterSeconds": 0}
    ),
    IndexSpec("fadmins", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec("logchannels", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec(
        "AUTH_USERS",
        (("id", 1),),
        "id_1",
        {"unique": True, "partialFilterExpression": {"id": {"$type": "number"}}},
    ),
    IndexSpec("AUTH_USERS", (("code", 1),), "code_1", {"sparse": True}),
    IndexSpec("chatbotto", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("gemini_convos", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec("antichannel", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("vanitas", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("ad_footers", (("created_at", 1),), "created_at_1", {"expireAfterSeconds": 3888000}),
    IndexSpec("bot2bot_settings", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("bot2bot_pending", (("token", 1),), "token_1", {"unique": True}),
    IndexSpec("bot2bot_pending", (("expires_at", 1),), "expires_at_1", {"expireAfterSeconds": 0}),
    IndexSpec("SFW_GROUPS", (("id", 1),), "id_1", {"unique": True}),
    IndexSpec(
        "approve_d", (("chat_id", 1), ("user_id", 1)), "uniq_approve_chat_user", {"unique": True}
    ),
    IndexSpec("users", (("bot_ids", 1),), "bot_ids_1", {}),
    IndexSpec("chats", (("bot_ids", 1),), "bot_ids_1", {}),
    IndexSpec("onofflevel", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("first_name", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec(
        "first_name",
        (("first_name", 1),),
        "uniq_display_name",
        {"unique": True, "partialFilterExpression": {"first_name": {"$type": "string", "$gt": ""}}},
    ),
    IndexSpec("levels_mutations", (("expires_at", 1),), "expires_at_1", {"expireAfterSeconds": 0}),
    IndexSpec("clone", (("token", 1),), "token_1", {"unique": True}),
    IndexSpec("clone", (("bot_id", 1),), "bot_id_1", {}),
    IndexSpec("clone", (("owner_id", 1),), "owner_id_1", {}),
    IndexSpec("dnd", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec(
        "feds",
        (("chat_id", 1),),
        "chat_id_1",
        {"unique": True, "partialFilterExpression": {"chat_id": {"$type": "number"}}},
    ),
    IndexSpec("playlists", (("playlist_id", 1),), "playlist_id_1", {"unique": True}),
    IndexSpec(
        "playlists", (("owner_id", 1), ("updated_at", -1), ("playlist_id", 1)), "owner_updated", {}
    ),
    IndexSpec(
        "playlists",
        (("access_mode", 1), ("trending_score", -1), ("playlist_id", 1)),
        "public_trending",
        {},
    ),
    IndexSpec(
        "playlists",
        (("access_mode", 1), ("updated_at", -1), ("playlist_id", 1)),
        "public_updated",
        {},
    ),
    IndexSpec(
        "playlists",
        (("server_chat_id", 1), ("updated_at", -1), ("playlist_id", 1)),
        "server_updated",
        {"sparse": True},
    ),
    IndexSpec(
        "playlists", (("editors", 1), ("updated_at", -1), ("playlist_id", 1)), "editor_updated", {}
    ),
    IndexSpec(
        "playlists",
        (("forked_from", 1), ("created_at", -1), ("playlist_id", 1)),
        "fork_created",
        {"sparse": True},
    ),
    IndexSpec(
        "playlists",
        (("owner_id", 1), ("is_liked", 1)),
        "owner_id_1_is_liked_1",
        {"unique": True, "partialFilterExpression": {"is_liked": True}},
    ),
    IndexSpec(
        "playlists",
        (("title", "text"), ("description", "text")),
        "playlist_text",
        {"weights": {"title": 10, "description": 3}},
    ),
    IndexSpec(
        "playlist_songs",
        (("playlist_id", 1), ("position", 1)),
        "playlist_id_1_position_1",
        {"unique": True},
    ),
    IndexSpec(
        "playlist_songs",
        (("playlist_id", 1), ("video_id", 1)),
        "playlist_id_1_video_id_1",
        {"unique": True},
    ),
    IndexSpec(
        "playlist_likes",
        (("playlist_id", 1), ("user_id", 1), ("kind", 1)),
        "playlist_id_1_user_id_1_kind_1",
        {"unique": True},
    ),
    IndexSpec(
        "playlist_likes",
        (("user_id", 1), ("kind", 1), ("created_at", -1)),
        "user_id_1_kind_1_created_at_-1",
        {},
    ),
    IndexSpec(
        "playlist_activity",
        (("playlist_id", 1), ("created_at", -1), ("_id", -1)),
        "activity_recent",
        {},
    ),
    IndexSpec(
        "playlist_reports",
        (("playlist_id", 1), ("reporter_id", 1)),
        "playlist_id_1_reporter_id_1",
        {"unique": True},
    ),
    IndexSpec(
        "playlist_reports", (("resolved", 1), ("created_at", -1)), "resolved_1_created_at_-1", {}
    ),
    IndexSpec(
        "playlist_plays",
        (("playlist_id", 1), ("expires_at", -1)),
        "playlist_id_1_expires_at_-1",
        {},
    ),
    IndexSpec("playlist_plays", (("expires_at", 1),), "expires_at_1", {"expireAfterSeconds": 0}),
    IndexSpec("requests", (("num", 1),), "num_1", {"unique": True}),
    IndexSpec(
        "requests",
        (("norm_query", 1), ("status", 1), ("chat_id", 1)),
        "norm_query_1_status_1_chat_id_1",
        {},
    ),
    IndexSpec(
        "requests", (("subscribers", 1), ("created_at", -1)), "subscribers_1_created_at_-1", {}
    ),
    IndexSpec(
        "request_limits", (("created_at", 1),), "created_at_1", {"expireAfterSeconds": 172800}
    ),
    IndexSpec("clone_invoices", (("expires_at", 1),), "expires_at_1", {"expireAfterSeconds": 0}),
    IndexSpec(
        "clone_payments", (("user_id", 1), ("created_at", -1)), "user_id_1_created_at_-1", {}
    ),
    IndexSpec("clone_operations", (("expires_at", 1),), "expires_at_1", {"expireAfterSeconds": 0}),
    IndexSpec("captcha_challenges", (("token", 1),), "token_1", {"unique": True}),
    IndexSpec(
        "captcha_challenges",
        (("bot_id", 1), ("chat_id", 1), ("welcome_id", 1)),
        "bot_id_chat_id_welcome_id",
        {},
    ),
    IndexSpec(
        "captcha_challenges", (("expires_at", 1),), "expires_at_1", {"expireAfterSeconds": 0}
    ),
    IndexSpec(
        "karma",
        (("user_id", 1),),
        "uniq_karma_user",
        {"unique": True, "partialFilterExpression": {"user_id": {"$type": "number"}}},
    ),
    IndexSpec(
        "karma",
        (("chat_id_toggle", 1),),
        "uniq_karma_toggle",
        {"unique": True, "partialFilterExpression": {"chat_id_toggle": {"$type": "number"}}},
    ),
    IndexSpec("autoapprove", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("antiflood_chats", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("birthday", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec("birthday", (("month", 1), ("day", 1)), "month_1_day_1", {}),
    IndexSpec("cleaner", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("startpic", (("bot_id", 1),), "bot_id_1", {"unique": True}),
    IndexSpec("pkang", (("user_id", 1),), "user_id_1", {"unique": True}),
    IndexSpec(
        "quotes",
        (("bot_id", 1), ("chat_id", 1), ("file_id", 1)),
        "uniq_quote_media",
        {"unique": True},
    ),
    IndexSpec(
        "quotes",
        (("bot_id", 1), ("chat_id", 1), ("score", -1), ("created_at", -1), ("_id", -1)),
        "quote_ranking",
        {},
    ),
    IndexSpec("join_times", (("chat_id", 1),), "chat_id_1", {"unique": True}),
    IndexSpec("join_times", (("updated_at", 1),), "updated_at_1", {"expireAfterSeconds": 3600}),
    IndexSpec(
        "playlist_mutations", (("expires_at", 1),), "expires_at_1", {"expireAfterSeconds": 0}
    ),
    IndexSpec(
        "requests",
        (("chat_id", 1), ("norm_query", 1)),
        "uniq_pending_request",
        {"unique": True, "partialFilterExpression": {"status": "pending"}},
    ),
)


_OPTIONS = (
    "unique",
    "sparse",
    "expireAfterSeconds",
    "partialFilterExpression",
    "weights",
    "collation",
)


def _keys_match(spec, actual):
    desired = list(spec.keys)
    existing = list(actual.get("key", []))
    if any(direction == "text" for _, direction in desired):
        return {field for field, direction in desired if direction == "text"} == set(
            actual.get("weights", {})
        ) and [(field, direction) for field, direction in desired if direction != "text"] == [
            (field, direction) for field, direction in existing if field not in {"_fts", "_ftsx"}
        ]
    return desired == existing


def _options_match(spec, actual):
    for key in _OPTIONS:
        default = False if key in {"unique", "sparse"} else None
        if spec.options.get(key, default) != actual.get(key, default):
            return False
    return True


async def ensure_indexes(database):
    definitions = defaultdict(list)
    for spec in INDEXES:
        definitions[spec.collection].append(spec)
    for name, specs in definitions.items():
        collection = database[name]
        existing = await collection.index_information()
        missing = []
        for spec in specs:
            if any(
                _keys_match(spec, index) and _options_match(spec, index)
                for index in existing.values()
            ):
                continue
            if spec.name in existing or any(
                _keys_match(spec, index) for index in existing.values()
            ):
                raise ValueError(f"Conflicting MongoDB index: {name}.{spec.name}")
            missing.append(IndexModel(list(spec.keys), name=spec.name, **spec.options))
        if missing:
            await collection.create_indexes(missing)
