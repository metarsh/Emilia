import logging
import os
import queue
import sys
from logging.handlers import RotatingFileHandler

import orjson
import redis.asyncio as redis
from pymongo import AsyncMongoClient
from pyrogram import Client
from redis.asyncio.retry import Retry
from redis.backoff import NoBackoff

from Emilia.config import Config
from Emilia.services.plugins import plugin_config
from Emilia.services.scheduler import ManagedScheduler
from Emilia.utils.ads import install_ad_hooks
from Emilia.utils.trace import TRACE_ID
from Emilia.utils.write_guard import install_write_guard

Config.validate()


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        emilia_extra = getattr(record, "emilia", None)
        if isinstance(emilia_extra, dict):
            log_record.update(emilia_extra)
        if "trace" not in log_record:
            tid = TRACE_ID.get()
            if tid is not None:
                log_record["trace"] = tid
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        from Emilia.utils.logging import redact

        return redact(orjson.dumps(log_record, default=str).decode())


_log_listener = None


def _setup_emilia_logging():
    global _log_listener

    from pathlib import Path

    from Emilia.utils.logging import DrainingQueueListener, RedactingQueueHandler

    log_queue = queue.Queue(maxsize=10000)
    stdout_h = logging.StreamHandler(sys.stdout)
    stdout_h.setFormatter(JSONFormatter())
    log_path = Path(Config.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_h = RotatingFileHandler(log_path, maxBytes=20_000_000, backupCount=3)
    os.chmod(log_path, 0o600)
    file_h.setFormatter(JSONFormatter())

    _log_listener = DrainingQueueListener(log_queue, stdout_h, file_h, respect_handler_level=True)
    _log_listener.start()

    qh = RedactingQueueHandler(log_queue)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers = [qh]

    logger = logging.getLogger("Emilia")
    logger.setLevel(logging.INFO)
    logger.propagate = True
    logger.handlers = []
    return logger


async def shutdown_logging():
    global _log_listener
    listener, _log_listener = _log_listener, None
    if listener is None:
        return
    from Emilia.utils.logging import stop_listener

    await stop_listener(listener)


for directory in (Config.SESSION_DIRECTORY, Config.STATE_DIR, Config.TEMP_DOWNLOAD_DIRECTORY):
    os.makedirs(directory, mode=0o700, exist_ok=True)

LOGGER = _setup_emilia_logging()

scheduler = ManagedScheduler(timezone=Config.TIMEZONE)

LOGGER.info("Starting %s", Config.BOT_NAME)
pyro_plugins = plugin_config()

mongo = AsyncMongoClient(
    Config.MONGO_DB_URL,
    maxPoolSize=Config.MONGO_MAX_POOL_SIZE,
    serverSelectionTimeoutMS=5000,
    connectTimeoutMS=5000,
    socketTimeoutMS=20000,
    retryWrites=True,
    tz_aware=True,
)
db = mongo[Config.MONGO_DATABASE]

redis_client = redis.Redis.from_pool(
    redis.BlockingConnectionPool.from_url(
        Config.REDIS_URL,
        password=Config.REDIS_PASSWORD,
        decode_responses=True,
        health_check_interval=30,
        socket_connect_timeout=5,
        socket_timeout=10,
        max_connections=Config.REDIS_MAX_CONNECTIONS,
        timeout=1,
        retry=Retry(NoBackoff(), 0),
    )
)

from Emilia.utils.metrics import MetricsLogHandler  # noqa: E402

if _log_listener is not None:
    _log_listener.handlers = _log_listener.handlers + (MetricsLogHandler(),)

pgram = Client(
    name="emilia_main",
    api_id=Config.API_ID,
    api_hash=Config.API_HASH,
    bot_token=Config.TOKEN,
    workers=32,
    plugins=pyro_plugins,
    workdir=Config.SESSION_DIRECTORY,
    sleep_threshold=10,
)
pgram.is_clone = False
pgram.owner_id = Config.OWNER_ID

install_ad_hooks()
install_write_guard()
