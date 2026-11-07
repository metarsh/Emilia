import asyncio
import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pymongo import UpdateOne
from pymongo.errors import BulkWriteError, PyMongoError

from Emilia.application import db
from Emilia.config import Config

LOGGER = logging.getLogger(__name__)


class WriteBuffer:
    def __init__(
        self,
        flush_interval=5,
        *,
        database=None,
        max_entries=None,
        batch_size=None,
        shutdown_timeout=None,
        recovery_path=None,
    ):
        self.flush_interval = flush_interval
        self.database = database if database is not None else db
        self.max_entries = (
            max_entries if max_entries is not None else Config.WRITE_BUFFER_MAX_ENTRIES
        )
        self.batch_size = batch_size if batch_size is not None else Config.WRITE_BUFFER_BATCH_SIZE
        self.shutdown_timeout = (
            shutdown_timeout
            if shutdown_timeout is not None
            else Config.WRITE_BUFFER_SHUTDOWN_TIMEOUT
        )
        if min(self.max_entries, self.batch_size, self.shutdown_timeout, flush_interval) <= 0:
            raise ValueError("Buffer capacity, batch size and timeouts must be positive")
        state_dir = Path(Config.STATE_DIR)
        self.recovery_path = (
            Path(recovery_path) if recovery_path else state_dir / "write-buffer.json"
        )
        self.users_buffer = {}
        self.chats_buffer = {}
        self.lock = asyncio.Lock()
        self._flush_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._stopping = False
        self._revision = 0
        self.running = False
        self.task = None

    async def start(self):
        async with self._lifecycle_lock:
            if self.running:
                return
            await self._recover()
            self._stopping = False
            self.running = True
            self.task = asyncio.create_task(self._loop(), name="write_buffer")

    async def stop(self):
        async with self._lifecycle_lock:
            await self._stop()

    async def _stop(self):
        self._stopping = True
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            self.task = None
        try:
            await asyncio.wait_for(self._drain(), timeout=self.shutdown_timeout)
        except asyncio.CancelledError:
            await self._save_recovery()
            raise
        except Exception:
            # Persist only at shutdown; steady-state writes stay off the disk.
            await self._save_recovery()
            LOGGER.error("Database backlog saved for the next startup")

    async def _make_room(self, buffer, key):
        async with self.lock:
            if self._stopping:
                raise RuntimeError("Database write buffer is stopping")
            if key in buffer or len(self.users_buffer) + len(self.chats_buffer) < self.max_entries:
                return
        await self._flush()
        async with self.lock:
            if (
                key not in buffer
                and len(self.users_buffer) + len(self.chats_buffer) >= self.max_entries
            ):
                raise BufferError("Database write backlog is full; update was not accepted")

    def _touch(self, entry):
        self._revision += 1
        entry["revision"] = self._revision

    async def add_user(
        self, user_id, username=None, chat_id=None, chat_title=None, forwarded=False, bot_id=None
    ):
        await self._make_room(self.users_buffer, user_id)
        async with self.lock:
            if self._stopping:
                raise RuntimeError("Database write buffer is stopping")
            if user_id not in self.users_buffer:
                if len(self.users_buffer) + len(self.chats_buffer) >= self.max_entries:
                    raise BufferError("Database write backlog is full; update was not accepted")
                self.users_buffer[user_id] = {"username": None, "chats": {}, "bot_ids": set()}
            entry = self.users_buffer[user_id]
            if username:
                entry["username"] = username
            if not forwarded and chat_id is not None:
                chat = entry["chats"].setdefault(
                    chat_id, {"chat_id": chat_id, "chat_title": chat_title}
                )
                if chat_title:
                    chat["chat_title"] = chat_title
            if bot_id:
                entry["bot_ids"].add(bot_id)
            self._touch(entry)

    async def add_chat(self, chat_id, chat_title, bot_id=None):
        await self._make_room(self.chats_buffer, chat_id)
        async with self.lock:
            if self._stopping:
                raise RuntimeError("Database write buffer is stopping")
            if chat_id not in self.chats_buffer:
                if len(self.users_buffer) + len(self.chats_buffer) >= self.max_entries:
                    raise BufferError("Database write backlog is full; update was not accepted")
                self.chats_buffer[chat_id] = {"chat_title": None, "bot_ids": set()}
            entry = self.chats_buffer[chat_id]
            if chat_title:
                entry["chat_title"] = chat_title
            if bot_id:
                entry["bot_ids"].add(bot_id)
            self._touch(entry)

    async def _loop(self):
        while self.running:
            await asyncio.sleep(self.flush_interval)
            try:
                await self._flush()
            except Exception:
                LOGGER.exception("Database buffer flush failed; backlog retained")

    @staticmethod
    def _update(entry, *, user):
        update = {"$setOnInsert": {"first_found_date": datetime.now(UTC)}}
        field = "username" if user else "chat_title"
        if entry.get(field):
            update["$set"] = {field: entry[field]}
        additions = {}
        if entry["bot_ids"]:
            additions["bot_ids"] = {"$each": list(entry["bot_ids"])}
        if additions:
            update["$addToSet"] = additions
        if not user or not entry["chats"]:
            return update
        # A title change must replace a membership by chat ID, rather than
        # append a second copy of the same chat on every retry.
        fields = {
            "first_found_date": {
                "$ifNull": ["$first_found_date", update["$setOnInsert"]["first_found_date"]]
            },
            "chats": {
                "$concatArrays": [
                    {
                        "$filter": {
                            "input": {"$ifNull": ["$chats", []]},
                            "as": "chat",
                            "cond": {
                                "$not": [
                                    {"$in": ["$$chat.chat_id", {"$literal": list(entry["chats"])}]}
                                ]
                            },
                        }
                    },
                    {"$literal": [dict(chat) for chat in entry["chats"].values()]},
                ]
            },
        }
        if entry.get("username"):
            fields["username"] = {"$literal": entry["username"]}
        if entry["bot_ids"]:
            fields["bot_ids"] = {
                "$setUnion": [
                    {"$ifNull": ["$bot_ids", []]},
                    {"$literal": list(entry["bot_ids"])},
                ]
            }
        return [{"$set": fields}]

    async def _flush_collection(self, collection, buffer, id_field, *, user):
        async with self.lock:
            batch = [
                (
                    key,
                    entry["revision"],
                    UpdateOne({id_field: key}, self._update(entry, user=user), upsert=True),
                )
                for key, entry in list(buffer.items())[: self.batch_size]
            ]
        if not batch:
            return True
        failed = set()
        try:
            await collection.bulk_write([item[2] for item in batch], ordered=False)
        except BulkWriteError as exc:
            details = exc.details
            if details.get("writeConcernErrors"):
                LOGGER.error("Database acknowledgement failed; retaining the whole batch")
                return False
            failed = {error["index"] for error in details.get("writeErrors", [])}
            if not failed:
                return False
            LOGGER.warning("Database batch retained %d failed update(s)", len(failed))
        except PyMongoError:
            LOGGER.exception("Database batch failed; retaining %d update(s)", len(batch))
            return False
        async with self.lock:
            for index, (key, revision, _) in enumerate(batch):
                current = buffer.get(key)
                if index not in failed and current and current["revision"] == revision:
                    del buffer[key]
                elif index in failed and current:
                    # A bad row cannot permanently starve later healthy rows.
                    buffer[key] = buffer.pop(key)
        return not failed

    async def _flush(self):
        async with self._flush_lock:
            users_ok = await self._flush_collection(
                self.database.users, self.users_buffer, "user_id", user=True
            )
            chats_ok = await self._flush_collection(
                self.database.chats, self.chats_buffer, "chat_id", user=False
            )
            if not self.users_buffer and not self.chats_buffer:
                await asyncio.to_thread(self.recovery_path.unlink, missing_ok=True)
            return users_ok and chats_ok

    async def _drain(self):
        while self.users_buffer or self.chats_buffer:
            if not await self._flush():
                await asyncio.sleep(min(self.flush_interval, 1))
        await asyncio.to_thread(self.recovery_path.unlink, missing_ok=True)

    async def _save_recovery(self):
        async with self.lock:
            payload = {
                "users": {
                    str(key): {
                        **entry,
                        "bot_ids": list(entry["bot_ids"]),
                        "chats": {str(k): dict(v) for k, v in entry["chats"].items()},
                    }
                    for key, entry in self.users_buffer.items()
                },
                "chats": {
                    str(key): {**entry, "bot_ids": list(entry["bot_ids"])}
                    for key, entry in self.chats_buffer.items()
                },
            }
        await asyncio.to_thread(self._write_recovery, payload)

    def _write_recovery(self, payload):
        self.recovery_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, name = tempfile.mkstemp(dir=self.recovery_path.parent, prefix=".write-buffer-")
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(payload, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.recovery_path)
        finally:
            Path(name).unlink(missing_ok=True)

    async def _recover(self):
        try:
            payload = await asyncio.to_thread(self.recovery_path.read_text)
        except FileNotFoundError:
            return
        data = json.loads(payload)
        async with self.lock:
            for label, buffer in (("users", self.users_buffer), ("chats", self.chats_buffer)):
                for key, entry in data.get(label, {}).items():
                    entry["bot_ids"] = set(entry["bot_ids"])
                    if label == "users":
                        entry["chats"] = {int(k): v for k, v in entry["chats"].items()}
                    current = buffer.get(int(key))
                    if current:
                        entry["bot_ids"].update(current["bot_ids"])
                        if label == "users":
                            entry["chats"].update(current["chats"])
                        field = "username" if label == "users" else "chat_title"
                        entry[field] = current.get(field) or entry.get(field)
                    self._touch(entry)
                    buffer[int(key)] = entry
        LOGGER.info("Recovered pending database updates")
