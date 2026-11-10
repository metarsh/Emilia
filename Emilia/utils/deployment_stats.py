import asyncio
import html
import platform
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import psutil
import pyrogram

from Emilia.application import LOGGER, db, redis_client
from Emilia.utils import metrics
from Emilia.utils.admins import get_time
from Emilia.utils.executors import run_in_thread
from Emilia.utils.process import run_process


ENTRY_METRICS = {
    "notes": ("notes", "array", "Saved notes"),
    "filters": ("filters", "array", "Saved filters"),
    "blocklists": ("blocklist_text", "array", "Blocked phrases"),
    "disable": ("disabled_items", "array", "Disabled commands"),
    "locks": ("locked", "array", "Locks"),
    "fbans": ("fbans", "object", "Federation ban entries"),
    "fsubs": ("my_subs", "array", "Federation subscription links"),
}
COUNT_METRICS = {
    "Known users": ("users", None),
    "Known chats": ("chats", None),
    "Registered clones": ("clone", None),
    "Member warnings": ("user_warnings", None),
    "Federations": ("feds", {"fed_id": {"$exists": True}}),
}
FEATURE_METRICS = {
    "Custom welcomes saved": ("welcome", {"welcome_message.text": {"$exists": True}}),
    "CAPTCHA enabled": ("welcome", {"captcha._captcha": True}),
    "Flood protection enabled": ("antiflood_chats", {"status": {"$exists": True, "$ne": "off"}}),
    "Timed flood protection enabled": ("antiflood_chats", {"timed_status": "on"}),
    "Automatic raid protection enabled": (
        "antiraid_data",
        {
            "$or": [
                {"auto_antiraid_threshold": {"$gt": 0}},
                {"auto_antiraid_threshold": {"$exists": False}},
            ]
        },
    ),
    "Join-request approval enabled": ("autoapprove", {"mode": {"$exists": True, "$ne": "off"}}),
    "Channel senders blocked": ("antichannel", {}),
    "Rules saved": ("rules", {"rules": {"$exists": True, "$nin": [None, ""]}}),
    "Log channels configured": ("logchannels", {"channel_id": {"$exists": True}}),
    "Levelling enabled": ("onofflevel", {"disabled": {"$ne": True}}),
    "Karma enabled": ("karma", {}),
    "Chatbot enabled": ("chatbotto", {}),
    "Night mode enabled": ("nightmode", {"chat_id": {"$lt": 0}}),
    "Bot commands allowed": ("bot2bot_settings", {"mode": {"$exists": True, "$ne": "off"}}),
}


@dataclass
class StatsSection:
    title: str
    rows: list[tuple] = field(default_factory=list)
    note: str = ""
    headers: tuple[str, ...] = ("Metric", "Value")

    def rich_html(self):
        header = "".join(f"<th>{html.escape(label)}</th>" for label in self.headers)
        rows = "".join(
            "<tr>" + "".join(f"<td>{html.escape(str(value))}</td>" for value in row) + "</tr>"
            for row in self.rows
        )
        note = f"<p>{html.escape(self.note)}</p>" if self.note else ""
        return f"<table><tr>{header}</tr>{rows}</table>{note}"

    def plain_text(self):
        lines = [self.title]
        for row in self.rows:
            if len(row) == 2:
                lines.append(f"{row[0]}: {row[1]}")
            else:
                lines.append(
                    f"{row[0]}: "
                    + "; ".join(
                        f"{header} {value}"
                        for header, value in zip(self.headers[1:], row[1:], strict=True)
                    )
                )
        if self.note:
            lines.append(self.note)
        return "\n".join(lines)


def format_bytes(value):
    if value is None:
        return "Unavailable"
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(value) < 1024:
            return f"{value:,.1f} {unit}"
        value /= 1024
    return f"{value:,.1f} PiB"


def number(value):
    return f"{value:,}" if isinstance(value, int) else "Unavailable"


async def _safe(label, operation):
    try:
        async with asyncio.timeout(10):
            return await operation()
    except Exception as error:
        LOGGER.warning("Stats: %s unavailable: %s", label, type(error).__name__)
        return None


async def _entries(collection, field_name, kind):
    value = f"${field_name}"
    if kind == "object":
        values = {"$cond": [{"$eq": [{"$type": value}, "object"]}, {"$objectToArray": value}, []]}
    else:
        values = {"$cond": [{"$isArray": value}, value, []]}
    size = {"$size": values}
    cursor = await collection.aggregate(
        [
            {"$project": {"size": size}},
            {
                "$group": {
                    "_id": None,
                    "entries": {"$sum": "$size"},
                    "parents": {"$sum": {"$cond": [{"$gt": ["$size", 0]}, 1, 0]}},
                }
            },
        ],
        maxTimeMS=3000,
    )
    rows = await cursor.to_list(length=1)
    return (rows[0]["entries"], rows[0]["parents"]) if rows else (0, 0)


def in_chats(value):
    if value is None:
        return "Unavailable"
    return f"{value:,} {'chat' if value == 1 else 'chats'}"


def entry_total(values, *, chats=False):
    if values is None:
        return "Unavailable"
    total, parents = values
    return f"{number(total)} in {in_chats(parents)}" if chats else number(total)


async def _database():
    names = set(await db.list_collection_names())
    semaphore = asyncio.Semaphore(6)

    async def count(label, name, query):
        if name not in names:
            return 0
        async with semaphore:
            return await _safe(
                label,
                lambda: (
                    db[name].estimated_document_count(maxTimeMS=3000)
                    if query is None
                    else db[name].count_documents(query, maxTimeMS=3000)
                ),
            )

    async def entries(name, field_name, kind, _label):
        if name not in names:
            return (0, 0)
        async with semaphore:
            return await _safe(name, lambda: _entries(db[name], field_name, kind))

    counts, totals, features, sizes = await asyncio.gather(
        asyncio.gather(*(count(label, *spec) for label, spec in COUNT_METRICS.items())),
        asyncio.gather(*(entries(name, *spec) for name, spec in ENTRY_METRICS.items())),
        asyncio.gather(*(count(label, *spec) for label, spec in FEATURE_METRICS.items())),
        _safe("database storage", lambda: db.command({"dbStats": 1, "scale": 1})),
    )
    totals = dict(zip(ENTRY_METRICS, totals, strict=True))
    summary = [
        ("Database data size", format_bytes((sizes or {}).get("dataSize"))),
        *((label, number(value)) for label, value in zip(COUNT_METRICS, counts, strict=True)),
        ("Saved notes", entry_total(totals["notes"], chats=True)),
        ("Saved filters", entry_total(totals["filters"], chats=True)),
        ("Federation ban entries", entry_total(totals["fbans"])),
    ]
    feature_rows = [
        (ENTRY_METRICS[name][2], entry_total(totals[name], chats=True))
        for name in ("blocklists", "disable", "locks")
    ]
    feature_rows.extend(
        (label, in_chats(value)) for label, value in zip(FEATURE_METRICS, features, strict=True)
    )
    # Date values follow the module's naive-UTC MongoDB representation.
    raids = await count(
        "Active raid protection",
        "antiraid_data",
        {"expiry_time": {"$gt": datetime.now(UTC).replace(tzinfo=None)}},
    )
    feature_rows.append(("Raid protection active now", in_chats(raids)))
    storage = [
        ("Allocated data", format_bytes((sizes or {}).get("storageSize"))),
        ("Indexes", format_bytes((sizes or {}).get("indexSize"))),
        ("Collections", number((sizes or {}).get("collections"))),
        ("Federation subscription links", entry_total(totals["fsubs"])),
    ]
    return summary, [
        StatsSection("Group features", feature_rows),
        StatsSection("Database", storage),
    ]


async def _system():
    process = psutil.Process()
    cpu = await run_in_thread(psutil.cpu_percent, interval=0.3)
    memory, disk = psutil.virtual_memory(), psutil.disk_usage("/")
    rows = [
        ("Host CPU usage", f"{cpu:.1f}%"),
        ("Host CPU cores", number(psutil.cpu_count())),
        ("Bot process memory", format_bytes(process.memory_info().rss)),
        (
            "Host memory in use",
            f"{format_bytes(memory.used)} / {format_bytes(memory.total)} ({memory.percent:.1f}%)",
        ),
        (
            "Root disk in use",
            f"{format_bytes(disk.used)} / {format_bytes(disk.total)} ({disk.percent:.1f}%)",
        ),
        ("Bot process threads", process.num_threads()),
        ("Host uptime", get_time(int(time.time() - psutil.boot_time()))),
        ("Python", platform.python_version()),
        ("Pyrogram", pyrogram.__version__),
    ]
    try:
        rows.append(("Bot process open files/sockets", process.num_fds()))
    except (AttributeError, psutil.Error):
        rows.append(("Bot process open files/sockets", "Unavailable"))
    try:
        rows.append(
            (
                "Host load (1 / 5 / 15 min)",
                " / ".join(f"{value:.2f}" for value in psutil.getloadavg()),
            )
        )
    except (OSError, AttributeError):
        pass
    return [
        StatsSection(
            "Process and host",
            rows,
            "Host totals include other services.",
        )
    ]


async def _usage():
    total, today, week, month, top = await asyncio.gather(
        metrics.total_commands(),
        metrics.commands_in_days(1),
        metrics.commands_in_days(7),
        metrics.commands_in_days(30),
        metrics.top_commands(5),
    )
    rows = [
        ("Since tracking began", number(total)),
        ("Today (UTC)", number(today)),
        ("Last 7 UTC dates", number(week)),
        ("Last 30 UTC dates", number(month)),
    ]
    sections = [
        StatsSection(
            "Command and callback activity",
            rows,
            "Handling attempts, including denials and callbacks. UTC date buckets.",
        )
    ]
    if top:
        labels = {
            "callback_query": "Button taps",
            "inline_query": "Inline searches",
            "stats|devstats": "/stats and /devstats",
        }
        sections.append(
            StatsSection(
                "Most used actions",
                [(labels.get(name, name), number(count)) for name, count in top],
                "",
            )
        )
    return sections


async def _logs():
    all_time, week, today = await asyncio.gather(
        metrics.log_counts(),
        metrics.log_counts_days(7),
        metrics.log_counts_days(1),
    )
    rows = [
        (label, number(today.get(level)), number(week.get(level)), number(all_time.get(level)))
        for level, label in [("WARNING", "Warnings"), ("ERROR", "Errors"), ("CRITICAL", "Critical")]
    ]
    return [
        StatsSection(
            "Application logs",
            rows,
            "Log entries; UTC date buckets.",
            headers=("Level", "Today", "7 days", "Total"),
        )
    ]


async def _redis():
    info, keys = await asyncio.gather(redis_client.info(), redis_client.dbsize())
    hits, misses = info.get("keyspace_hits"), info.get("keyspace_misses")
    rate = "Unavailable"
    if hits is not None and misses is not None:
        rate = f"{hits / (hits + misses):.1%}" if hits + misses else "No lookups yet"
    memory_limit = info.get("maxmemory")
    rows = [
        ("Memory in use", format_bytes(info.get("used_memory"))),
        (
            "Memory limit",
            "No configured limit" if memory_limit == 0 else format_bytes(memory_limit),
        ),
        ("Keys in configured Redis database", number(keys)),
        ("Connected clients", number(info.get("connected_clients"))),
        ("Blocked clients", number(info.get("blocked_clients"))),
        ("Operations per second", number(info.get("instantaneous_ops_per_sec"))),
        ("Key lookup hit rate", rate),
        ("Evicted keys", number(info.get("evicted_keys"))),
        ("Rejected connections", number(info.get("rejected_connections"))),
        (
            "Redis uptime",
            get_time(info["uptime_in_seconds"]) if "uptime_in_seconds" in info else "Unavailable",
        ),
    ]
    return [
        StatsSection(
            "Redis cache and counters",
            rows,
            "Server totals; keys belong to the configured database.",
        )
    ]


async def _runtime():
    from Emilia.services.clone_runtime import clone_manager

    from Emilia.application import pgram

    running = [
        entry["client"] for entry in clone_manager.clones.values() if entry["state"] == "running"
    ]
    clients = {id(client): client for client in [pgram, *running]}
    pending = sum(client.dispatcher.updates_queue.qsize() for client in clients.values())
    rows = [
        ("Clones running here", number(len(running))),
        ("Pending Telegram updates here", number(pending)),
    ]
    try:
        revision = await run_process("git", "rev-parse", "--short", "HEAD", timeout=2)
        rows.append(
            (
                "Code revision",
                revision.stdout.strip() if revision.returncode == 0 else "Unavailable",
            )
        )
    except (OSError, TimeoutError):
        rows.append(("Code revision", "Unavailable"))
    users = sys.modules.get("Emilia.database.users")
    if users is not None:
        buffer = users.WRITE_BUFFER
        rows.append(("Pending database writes here", number(len(buffer.users) + len(buffer.chats))))
    return [StatsSection("Live services (this process)", rows)]


async def _music():
    music = sys.modules.get("Emilia.modules.music.core.call")
    store = sys.modules.get("Emilia.modules.music.utils.store")
    if music is None or store is None:
        return [StatsSection("Music", [("Service in this process", "Not loaded")])]
    rows = [("Active music voice chats here", number(len(await music.emilia_call.calls)))]
    for label, cache, pattern in (
        ("Stored music queues", store.music_state, "queue:*"),
        ("Cached song file IDs", store.music_cache, "*"),
        ("Cached song metadata", store.music_meta, "*"),
    ):
        count = 0
        async for _ in redis_client.scan_iter(match=cache._rkey(pattern), count=200):
            count += 1
        rows.append((label, number(count)))
    return [
        StatsSection(
            "Music",
            rows,
            "Stored queues may be empty.",
        )
    ]


async def build_dashboard():
    builders = [
        ("Database", _database),
        ("Process and host", _system),
        ("Activity", _usage),
        ("Logged issues", _logs),
        ("Redis", _redis),
        ("Live services", _runtime),
        ("Music", _music),
    ]
    results = await asyncio.gather(*(_safe(title, builder) for title, builder in builders))
    summary = StatsSection(
        "Bot stats", [("Process uptime", get_time(int(time.time() - metrics.PROCESS_START)))]
    )
    sections = []
    for (title, _), result in zip(builders, results, strict=True):
        if result is None:
            if title == "Database":
                summary.rows.extend(
                    (label, "Unavailable")
                    for label in (
                        "Database data size",
                        "Known users",
                        "Known chats",
                        "Registered clones",
                        "Saved notes",
                        "Saved filters",
                        "Member warnings",
                        "Federations",
                        "Federation ban entries",
                    )
                )
            sections.append(
                StatsSection(
                    title,
                    [("Status", "Unavailable")],
                    "",
                )
            )
        elif title == "Database":
            rows, database_sections = result
            summary.rows.extend(rows)
            sections.extend(database_sections)
        else:
            sections.extend(result)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    rich = f"<p><b>Bot stats</b></p>" + summary.rich_html()
    rich += "".join(
        f"<details><summary>{html.escape(section.title)}</summary>{section.rich_html()}</details>"
        for section in sections
    )
    rich += f"<footer>{timestamp}</footer>"
    plain = [
        summary.plain_text(),
        *(section.plain_text() for section in sections),
        f"Snapshot: {timestamp}",
    ]
    return rich, "\n\n".join(plain)


def plain_chunks(text, limit=3800):
    chunk = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if chunk:
                yield chunk.rstrip()
                chunk = ""
            yield line[:limit]
            line = line[limit:]
        if len(chunk) + len(line) > limit:
            yield chunk.rstrip()
            chunk = ""
        chunk += line
    if chunk:
        yield chunk.rstrip()
