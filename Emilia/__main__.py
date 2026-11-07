import asyncio
import importlib
import inspect
import os
import sys
import time
from pathlib import Path

from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from Emilia.config import Config
from Emilia.services.plugins import plugin_config

HEARTBEAT_FILE = Path("/tmp/emilia_heartbeat")


def import_modules() -> None:
    from Emilia.application import LOGGER
    from Emilia.locales.help import HELP_PAGES

    modules = plugin_config()["include"]
    for name in modules:
        importlib.import_module("Emilia.modules." + name)
    LOGGER.info("Loaded %d handler modules and %d help pages", len(modules), len(HELP_PAGES))


async def heartbeat() -> None:
    from Emilia.application import LOGGER, db, pgram, redis_client
    from Emilia.services.clone_runtime import clone_manager

    while True:
        started = time.monotonic()
        healthy = False
        try:
            await asyncio.wait_for(
                asyncio.gather(db.command("ping"), redis_client.ping()), timeout=10
            )
            healthy = bool(pgram.is_connected)
            LOGGER.info(
                "heartbeat",
                extra={
                    "emilia": {
                        "event": "heartbeat",
                        "healthy": healthy,
                        "clones": len(clone_manager.clones),
                        "latency_ms": round((time.monotonic() - started) * 1000),
                    }
                },
            )
        except (PyMongoError, RedisError, TimeoutError):
            LOGGER.exception("Service health check failed")
        if healthy:
            HEARTBEAT_FILE.touch()
        else:
            HEARTBEAT_FILE.unlink(missing_ok=True)
        await asyncio.sleep(60)


async def _shutdown() -> None:
    from Emilia.application import LOGGER, mongo, pgram, redis_client, scheduler
    from Emilia.services.client_lifecycle import stop_client
    from Emilia.utils import tasks
    from Emilia.utils.cache import SimpleCache

    async def run_step(name, action):
        try:
            result = action()
            if inspect.isawaitable(result):
                await result
        except Exception:
            LOGGER.exception("Shutdown failed: %s", name)

    helper = sys.modules.get("Emilia.utils.anime")
    nightmode = sys.modules.get("Emilia.modules.nightmode")
    for item in (getattr(helper, "j1", None), getattr(nightmode, "scheduler", None), scheduler):
        if item is not None and item.running:
            await run_step("scheduler", item.aclose)
    await run_step("background tasks", tasks.shutdown_background_tasks)
    for name in ("Emilia.modules.clone", "Emilia.modules.chatbot"):
        module = sys.modules.get(name)
        if module:
            action = getattr(module, "shutdown_all_clones", None) or getattr(
                module, "shutdown_chatbot", None
            )
            if action:
                await run_step(name, action)
    module = sys.modules.get("Emilia.modules.music.core.call")
    if module:
        await run_step("music", module.shutdown_music)
    youtube = sys.modules.get("Emilia.modules.music.core.youtube")
    if youtube:
        await run_step("youtube executors", youtube.shutdown_youtube)
    await run_step("main bot", lambda: stop_client(pgram))
    users = sys.modules.get("Emilia.database.users")
    if users:
        await run_step("write buffer", users.WRITE_BUFFER.stop)
    for cache in tuple(SimpleCache._instances):
        await run_step("cache", cache.stop)
    from Emilia.utils import executors
    from Emilia.utils.http import close_http_clients

    await run_step("http", close_http_clients)
    await run_step("executors", executors.shutdown_executors)
    await run_step("redis", redis_client.aclose)
    await run_step("mongo", mongo.close)
    await run_step("heartbeat", lambda: HEARTBEAT_FILE.unlink(missing_ok=True))
    LOGGER.info("Services stopped")
    application = sys.modules.get("Emilia.application")
    if application and hasattr(application, "shutdown_logging"):
        await run_step("logging", application.shutdown_logging)


async def main() -> None:
    from pyrogram import idle

    HEARTBEAT_FILE.unlink(missing_ok=True)
    Config.validate()
    try:
        from Emilia.application import LOGGER, db, pgram, redis_client, scheduler

        await asyncio.wait_for(asyncio.gather(db.command("ping"), redis_client.ping()), timeout=15)
        from Emilia.database.indexes import ensure_indexes

        await ensure_indexes(db)
        from Emilia.custom_filter import flush_pending_handlers
        from Emilia.database.users import WRITE_BUFFER
        from Emilia.modules.clone import clone_health_loop, clone_start_up
        from Emilia.utils.anime import j1
        from Emilia.utils.cache import start_cache_cleanup
        from Emilia.utils.tasks import spawn

        import_modules()
        await WRITE_BUFFER.start()
        await asyncio.wait_for(pgram.start(), timeout=Config.CLONE_START_TIMEOUT)
        Config.BOT_USERNAME = pgram.me.username or Config.BOT_USERNAME
        flush_pending_handlers()
        scheduler.start()
        from Emilia.modules.music.core.call import assistant, emilia_call
        from Emilia.modules.music.core.youtube import start_cleanup_task
        from Emilia.modules.music.playlist.core import start_trending_refresh_task

        await asyncio.wait_for(assistant.start(), timeout=Config.CLONE_START_TIMEOUT)
        await asyncio.wait_for(emilia_call.start(), timeout=Config.CLONE_START_TIMEOUT)
        spawn(start_cleanup_task(), name="music_cleanup")
        spawn(start_trending_refresh_task(), name="playlist_trending")
        from Emilia.modules.nightmode import start_nightmode_scheduler

        start_nightmode_scheduler(pgram)
        j1.start()
        spawn(start_cache_cleanup(), name="cache_cleanup")
        spawn(clone_start_up(), name="clone_startup")
        spawn(clone_health_loop(), name="clone_health")
        from Emilia.services.clone_payments import payment_recovery_loop
        from Emilia.services.clones import renew_leases

        spawn(renew_leases(), name="clone_leases")
        spawn(payment_recovery_loop(pgram), name="clone_payments")
        from Emilia.services.database_recovery import database_recovery_loop

        spawn(database_recovery_loop(), name="database_recovery")
        spawn(heartbeat(), name="heartbeat")
        from Emilia.modules.backup import send

        spawn(send(), name="startup_backup")
        LOGGER.info("%s is online", Config.BOT_NAME)
        await idle()
    finally:
        if "Emilia.application" in sys.modules:
            from Emilia.utils.tasks import finish_cleanup

            await finish_cleanup(_shutdown())


def run() -> None:
    os.umask(0o077)
    try:
        import uvloop
    except ImportError:
        asyncio.run(main())
    else:
        uvloop.run(main())


if __name__ == "__main__":
    run()
