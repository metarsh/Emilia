import time

import psutil
from ntgcalls import BaseRTCException
from pymongo.errors import PyMongoError
from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError
from pyrogram.types import LinkPreviewOptions
from redis.exceptions import RedisError

from Emilia.application import LOGGER, db, redis_client
from Emilia.custom_filter import auth
from Emilia.locales import tr
from Emilia.utils import metrics
from Emilia.utils.admins import get_time
from Emilia.utils.executors import run_in_thread

_COLLECTIONS = [
    ("Users", "users"),
    ("Chats", "chats"),
    ("Notes", "notes"),
    ("Filters", "filters"),
    ("Feds", "feds"),
    ("Fbans", "fbans"),
    ("Warns", "user_warnings"),
    ("Blocklists", "blocklists"),
    ("Welcome", "welcome"),
    ("AFK", "afk"),
]


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}PB"


async def _system_section() -> str:
    proc = psutil.Process()
    vm = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    try:
        load1, load5, load15 = psutil.getloadavg()
        load = f"{load1:.2f} {load5:.2f} {load15:.2f}"
    except (OSError, AttributeError):
        load = "n/a"
    cpu = await run_in_thread(psutil.cpu_percent, interval=0.3)
    rss = proc.memory_info().rss
    with proc.oneshot():
        threads = proc.num_threads()
        try:
            fds = proc.num_fds()
        except (AttributeError, psutil.Error):
            fds = "n/a"
    return tr(
        "devstats.system_cpu_cores_load_ram_disk_proc_rss",
        cpu=cpu,
        psutil=psutil.cpu_count(),
        load=load,
        used=_fmt_bytes(vm.used),
        total=_fmt_bytes(vm.total),
        percent=vm.percent,
        used_2=_fmt_bytes(disk.used),
        total_2=_fmt_bytes(disk.total),
        percent_2=disk.percent,
        rss=_fmt_bytes(rss),
        threads=threads,
        fds=fds,
    )


async def _uptime_section() -> str:
    now = int(time.time())
    process = get_time(now - int(metrics.PROCESS_START))
    sys_boot = get_time(now - int(psutil.boot_time()))
    return tr("devstats.uptime_process_host", process=process, sys_boot=sys_boot)


async def _clones_section() -> str:
    from Emilia.services.clone_runtime import clone_manager

    return tr("devstats.clones_running", count=len(clone_manager.clones))


async def _db_section() -> str:
    lines = ["<b>🗄 MongoDB</b>"]
    for label, attr in _COLLECTIONS:
        try:
            count = await getattr(db, attr).estimated_document_count()
        except PyMongoError:
            count = "err"
        lines.append(tr("devstats.db_section_label_count", label=label, count=count))
    return "\n".join(lines)


async def _redis_section() -> str:
    try:
        info = await redis_client.info()
        mem = info.get("used_memory_human", "?")
        clients = info.get("connected_clients", "?")
        ops = info.get("instantaneous_ops_per_sec", "?")
        up = info.get("uptime_in_seconds", 0)
        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses
        hitrate = f"{(hits / total * 100):.1f}%" if total else "n/a"
        return tr(
            "devstats.redis_mem_clients_ops_s_hit_rate_uptime",
            mem=mem,
            clients=clients,
            ops=ops,
            hitrate=hitrate,
            uptime=get_time(up),
        )
    except RedisError:
        return tr("devstats.redis_unavailable")


async def _usage_section() -> str:
    total = await metrics.total_commands()
    day = await metrics.commands_in_days(1)
    week = await metrics.commands_in_days(7)
    month = await metrics.commands_in_days(30)
    top = await metrics.top_commands(10)
    lines = [
        tr("devstats.command_usage"),
        tr("devstats.total", total=total),
        tr("devstats.activity_periods", day=day, week=week, month=month),
    ]
    if top:
        lines.append("• Top:")
        for name, cnt in top:
            lines.append(tr("devstats.usage_section_name_cnt", name=name, cnt=cnt))
    return "\n".join(lines)


async def _errors_section() -> str:
    allt = await metrics.log_counts()
    week = await metrics.log_counts_days(7)
    day = await metrics.log_counts_days(1)
    return tr(
        "devstats.logs_warn_err_crit_all_7d_24h",
        warning=allt["WARNING"],
        error=allt["ERROR"],
        critical=allt["CRITICAL"],
        warning_2=week["WARNING"],
        error_2=week["ERROR"],
        critical_2=week["CRITICAL"],
        warning_3=day["WARNING"],
        error_3=day["ERROR"],
        critical_3=day["CRITICAL"],
    )


async def _music_section() -> str:
    try:
        from Emilia.application import redis_client
        from Emilia.modules.music.core.call import emilia_call
        from Emilia.modules.music.utils.store import music_cache, music_meta, music_state

        active_vcs = len(await emilia_call.calls)

        counts = []
        for cache, pattern in ((music_cache, "*"), (music_meta, "*"), (music_state, "queue:*")):
            count = 0
            async for _ in redis_client.scan_iter(match=cache._rkey(pattern), count=200):
                count += 1
            counts.append(count)
        cached_files, cached_meta, queued_chats = counts

        stats = tr(
            "devstats.music_system_active_vc_queued_chats_cached_songs",
            active_vcs=active_vcs,
            queued_chats=queued_chats,
            cached_files=cached_files,
            cached_meta=cached_meta,
        )
        return stats
    except (RedisError, BaseRTCException):
        return tr("devstats.music_system_n")


@auth(pattern="devstats")
async def devstats(client, message):
    msg = await message.reply_text(tr("devstats.gathering_stats"))
    sections = []
    for builder in (
        _uptime_section,
        _system_section,
        _clones_section,
        _music_section,
        _usage_section,
        _errors_section,
        _db_section,
        _redis_section,
    ):
        try:
            sections.append(await builder())
        except Exception:
            LOGGER.warning(f"devstats: {builder.__name__} failed", exc_info=True)
            sections.append(f"<i>{builder.__name__} failed</i>")
    text = "\n\n".join(sections)
    try:
        await msg.edit_text(
            text,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except (RPCError, OSError):
        await msg.edit_text(tr("devstats.stats_too_long_or_render_failed_check"))
