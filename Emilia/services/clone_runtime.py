import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from weakref import WeakValueDictionary

from pyrogram import Client
from pyrogram.errors import (
    AccessTokenExpired,
    AccessTokenInvalid,
    AuthKeyUnregistered,
    SessionRevoked,
)

from Emilia.application import LOGGER
from Emilia.config import Config
from Emilia.custom_filter import register_expired_callback_catchall
from Emilia.services.client_lifecycle import stop_client
from Emilia.services.plugins import plugin_config
from Emilia.utils.tasks import finish_cleanup


def _remove_session_files(bot_id):
    name = f"emilia_clone_{int(bot_id)}"
    for directory in (Path(Config.SESSION_DIRECTORY), Path.cwd()):
        for suffix in (".session", ".session-journal", ".session-wal", ".session-shm"):
            try:
                (directory / f"{name}{suffix}").unlink(missing_ok=True)
            except OSError as exc:
                LOGGER.warning("Could not remove clone session %s: %s", bot_id, type(exc).__name__)


class CloneManager:
    def __init__(self):
        self.clones = {}
        self._locks = WeakValueDictionary()
        self._starts = asyncio.Semaphore(Config.CLONE_START_CONCURRENCY)

    @asynccontextmanager
    async def bot_lock(self, bot_id):
        lock = self._locks.setdefault(int(bot_id), asyncio.Lock())
        async with lock:
            yield

    async def _shutdown(self, client):
        await stop_client(client)

    async def _start_clone(self, owner_id, bot_token, bot_id):
        entry = self.clones.get(bot_id)
        if entry and entry.get("state") == "running" and entry["client"].is_connected:
            if entry["owner_id"] != owner_id or entry["bot_token"] != bot_token:
                return False, None, None
            return True, entry["bot_username"], entry["bot_name"]
        if entry:
            await self._stop_clone(bot_id)
        client = None
        try:
            async with asyncio.timeout(Config.CLONE_START_TIMEOUT), self._starts:
                Path(Config.SESSION_DIRECTORY).mkdir(parents=True, exist_ok=True)
                client = Client(
                    name=f"emilia_clone_{int(bot_id)}",
                    api_id=Config.API_ID,
                    api_hash=Config.API_HASH,
                    bot_token=bot_token,
                    plugins=plugin_config(clone=True),
                    sleep_threshold=10,
                    workdir=Config.SESSION_DIRECTORY,
                )
                client.is_clone = True
                client.owner_id = owner_id
                client.bot_id = bot_id
                self.clones[bot_id] = {
                    "client": client,
                    "bot_token": bot_token,
                    "owner_id": owner_id,
                    "bot_id": bot_id,
                    "state": "starting",
                }
                register_expired_callback_catchall(client)
                await client.start()
                me = client.me
                if not me or me.id != bot_id:
                    raise ValueError("Clone identity mismatch")
                self.clones[bot_id].update(
                    state="running",
                    bot_username=me.username,
                    bot_name=me.first_name,
                )
                return True, me.username, me.first_name
        except (Exception, asyncio.CancelledError) as exc:
            if client is not None:
                await self._stop_clone(bot_id)
            if isinstance(exc, asyncio.CancelledError):
                raise
            LOGGER.error("Failed to start clone %s: %s", bot_id, type(exc).__name__)
            if isinstance(
                exc, (SessionRevoked, AuthKeyUnregistered, AccessTokenInvalid, AccessTokenExpired)
            ):
                _remove_session_files(bot_id)
            return False, None, None

    async def _stop_clone(self, bot_id):
        entry = self.clones.get(bot_id)
        if not entry:
            return False

        async def cleanup():
            try:
                await self._shutdown(entry["client"])
            except Exception:
                entry["state"] = "stop_failed"
                raise
            self.clones.pop(bot_id, None)
            return True

        return await finish_cleanup(cleanup())

    async def stop_clone(self, bot_id):
        async with self.bot_lock(bot_id):
            return await self._stop_clone(bot_id)

    async def stop_all_clones(self):
        results = await asyncio.gather(
            *(self.stop_clone(bot_id) for bot_id in list(self.clones)),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, Exception)]
        if failures:
            raise ExceptionGroup("Clone shutdown failures", failures)


clone_manager = CloneManager()
