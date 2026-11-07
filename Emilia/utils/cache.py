import asyncio
import hashlib
import inspect
import logging
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from functools import wraps

import orjson

from Emilia.config import Config
from Emilia.utils.tasks import finish_cleanup

LOGGER = logging.getLogger(__name__)


class SimpleCache:
    _instances = []

    def __init__(
        self,
        default_ttl=300,
        namespace="cache",
        max_l1_entries=None,
        *,
        redis_client=None,
    ):
        self._l1_cache = OrderedDict()
        self._max_l1 = Config.CACHE_MAX_L1_ENTRIES if max_l1_entries is None else max_l1_entries
        if not isinstance(self._max_l1, int) or isinstance(self._max_l1, bool) or self._max_l1 < 1:
            raise ValueError("The L1 cache bound must be a positive integer")
        self._default_ttl = default_ttl
        self._redis = redis_client
        self._pubsub = None
        self._listener_task = None
        prefix = Config.CACHE_NAMESPACE.strip(":")
        self._namespace = f"{prefix}:{namespace}" if prefix else namespace
        self._instance_id = uuid.uuid4().hex
        self._channel_name = f"cache_inv:{self._namespace}"
        self._running = False
        self._inflight = {}
        self._invalidated = set()
        self._key_locks = {}
        self._epoch = 0
        self._start_lock = asyncio.Lock()
        SimpleCache._instances.append(self)

    def _rkey(self, key):
        return f"{self._namespace}:{key}"

    @asynccontextmanager
    async def _mutation_lock(self, key):
        entry = self._key_locks.setdefault(key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if not entry[1]:
                self._key_locks.pop(key, None)

    def _invalidate_all(self):
        self._epoch += 1
        self._l1_cache.clear()
        self._invalidated.update(self._inflight)

    async def start(self):
        async with self._start_lock:
            if self._running:
                if self._listener_task.done():
                    self._listener_task.result()
                return
            if self._redis is None:
                from Emilia.application import redis_client

                self._redis = redis_client
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            try:
                await self._pubsub.subscribe(self._channel_name)
                while True:
                    acknowledgement = await self._pubsub.get_message(timeout=1.0)
                    if acknowledgement and acknowledgement["type"] == "subscribe":
                        break
            except BaseException:
                await finish_cleanup(self._pubsub.aclose())
                self._pubsub = None
                raise
            self._running = True
            # Every cache shares the application's pool. PubSub reserves its own
            # connection and polls within the pool's ordinary socket timeout.
            self._listener_task = asyncio.create_task(
                self._listen_for_invalidation(), name=f"cache:{self._namespace}"
            )

    async def _ensure_running(self):
        if not self._running:
            await self.start()
        elif self._listener_task.done():
            self._listener_task.result()

    async def stop(self):
        self._running = False
        if self._listener_task:
            self._listener_task.cancel()
            await asyncio.gather(self._listener_task, return_exceptions=True)
            self._listener_task = None
        if self._pubsub is not None:
            await self._pubsub.aclose()
            self._pubsub = None
        pending = list(self._inflight.values())
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        self._invalidate_all()
        # The application's lifecycle owns and closes the shared Redis pool.

    def _is_expired(self, entry):
        return time.monotonic() >= entry["expires"]

    def _store_l1(self, key, value, expires):
        self._l1_cache[key] = {"value": value, "expires": expires}
        self._l1_cache.move_to_end(key)
        while len(self._l1_cache) > self._max_l1:
            self._l1_cache.popitem(last=False)

    def _invalidate(self, key):
        self._epoch += 1
        self._l1_cache.pop(key, None)
        if key in self._inflight:
            self._invalidated.add(key)

    async def lookup(self, key):
        """Return (found, value), including cached None and empty results."""
        await self._ensure_running()
        key = str(key)
        entry = self._l1_cache.get(key)
        if entry is not None:
            if not self._is_expired(entry):
                self._l1_cache.move_to_end(key)
                return True, entry["value"]
            del self._l1_cache[key]
        for _ in range(2):
            started = time.monotonic()
            epoch = self._epoch
            pipe = self._redis.pipeline(transaction=True)
            pipe.get(self._rkey(key))
            pipe.pttl(self._rkey(key))
            raw, remaining = await pipe.execute()
            if epoch != self._epoch:
                continue
            if raw is not None and remaining != -2:
                try:
                    value = orjson.loads(raw)
                except orjson.JSONDecodeError:
                    LOGGER.warning("Invalid cached JSON: %s", self._namespace)
                    break
                ttl = self._default_ttl if remaining == -1 else remaining / 1000
                if ttl > 0:
                    self._store_l1(key, value, started + min(ttl, self._default_ttl))
                    return True, value
            return False, None
        return False, None

    async def get(self, key):
        _, value = await self.lookup(key)
        return value

    async def set(self, key, value, ttl=None):
        await self._ensure_running()
        key = str(key)
        self._invalidate(key)
        async with self._mutation_lock(key):
            self._invalidate(key)
            await self._set(key, value, ttl)

    async def _set(self, key, value, ttl=None):
        ttl = self._default_ttl if ttl is None else ttl
        if ttl <= 0:
            await self._delete_redis(key)
            return
        encoded = orjson.dumps(value)
        milliseconds = max(1, int(ttl * 1000))
        started = time.monotonic()
        epoch = self._epoch
        pipe = self._redis.pipeline(transaction=True)
        pipe.set(self._rkey(key), encoded, px=milliseconds)
        pipe.publish(self._channel_name, orjson.dumps({"i": self._instance_id, "k": key}))
        await pipe.execute()
        if epoch == self._epoch:
            self._store_l1(key, value, started + milliseconds / 1000)

    async def delete(self, key):
        await self._ensure_running()
        key = str(key)
        self._invalidate(key)
        async with self._mutation_lock(key):
            self._invalidate(key)
            await self._delete_redis(key)

    async def _delete_redis(self, key):
        pipe = self._redis.pipeline(transaction=True)
        pipe.delete(self._rkey(key))
        pipe.publish(self._channel_name, orjson.dumps({"i": self._instance_id, "k": key}))
        await pipe.execute()
        self._invalidate(key)

    async def clear(self):
        await self._ensure_running()
        self._invalidate_all()
        batch = []
        async for key in self._redis.scan_iter(match=f"{self._namespace}:*", count=500):
            batch.append(key)
            if len(batch) >= 500:
                await self._redis.unlink(*batch)
                batch.clear()
        if batch:
            await self._redis.unlink(*batch)
        await self._redis.publish(
            self._channel_name, orjson.dumps({"i": self._instance_id, "k": "__ALL__"})
        )
        self._invalidate_all()

    async def _listen_for_invalidation(self):
        try:
            while self._running:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )
                if message is None:
                    await asyncio.sleep(0)
                    continue
                try:
                    payload = orjson.loads(message["data"])
                except (orjson.JSONDecodeError, KeyError, TypeError):
                    continue
                if not isinstance(payload, dict) or payload.get("i") == self._instance_id:
                    continue
                key = payload.get("k")
                if key == "__ALL__":
                    self._invalidate_all()
                elif isinstance(key, str):
                    self._invalidate(key)
        finally:
            self._invalidate_all()
            await self._pubsub.aclose()
            self._pubsub = None

    def cleanup_expired(self):
        for key in list(self._l1_cache):
            if self._is_expired(self._l1_cache[key]):
                self._l1_cache.pop(key, None)

    async def get_or_load(self, key, loader, ttl=None):
        key = str(key)
        found, value = await self.lookup(key)
        if found:
            return value
        task = self._inflight.get(key)
        if task is None:
            if len(self._inflight) >= self._max_l1:
                return await loader()

            async def load():
                result = await loader()
                async with self._mutation_lock(key):
                    if key not in self._invalidated:
                        await self._set(key, result, ttl)
                        if key in self._invalidated:
                            # An event received during the Redis write means
                            # the loader raced a database mutation elsewhere.
                            self._l1_cache.pop(key, None)
                            await self._delete_redis(key)
                return result

            task = asyncio.create_task(load(), name=f"cache_load:{self._namespace}")
            self._inflight[key] = task

            def done(completed):
                if self._inflight.get(key) is completed:
                    self._inflight.pop(key, None)
                    self._invalidated.discard(key)
                if not completed.cancelled():
                    completed.exception()

            task.add_done_callback(done)
        return await asyncio.shield(task)


locks_cache = SimpleCache(120, "locks")
admin_cache = SimpleCache(300, "admin")
blocklist_cache = SimpleCache(180, "blocklist")
linked_chat_cache = SimpleCache(900, "linked_chat")
anonymous_admin_cache = SimpleCache(300, "anon_admin")
approvals_cache = SimpleCache(180, "approvals")
playmenu_cache = SimpleCache(300, "playmenu")
autoplay_cache = SimpleCache(300, "autoplay")


def cached_db_call(cache_instance, ttl=None):
    def decorator(func):
        signature = inspect.signature(func)

        def cache_key(*args, **kwargs):
            arguments = signature.bind(*args, **kwargs)
            arguments.apply_defaults()
            identity = [func.__module__, func.__qualname__, arguments.arguments]
            return hashlib.sha256(
                orjson.dumps(identity, option=orjson.OPT_SORT_KEYS, default=repr)
            ).hexdigest()

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await cache_instance.get_or_load(
                cache_key(*args, **kwargs), lambda: func(*args, **kwargs), ttl
            )

        async def invalidate(*args, **kwargs):
            await cache_instance.delete(cache_key(*args, **kwargs))

        wrapper.cache_key = cache_key
        wrapper.invalidate = invalidate
        return wrapper

    return decorator


async def start_cache_cleanup():
    while True:
        for cache in list(SimpleCache._instances):
            if not cache._running:
                await cache.start()
            cache.cleanup_expired()
        await asyncio.sleep(60)
