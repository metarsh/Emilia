import asyncio
import base64
import logging
import sqlite3
import struct
from contextlib import closing
from pathlib import Path

from pyrogram import Client
from pyrogram.storage.sqlite_storage import PROD, SCHEMA, TEST, SQLiteStorage
from pyrogram.storage.storage import Storage
from pytgcalls import PyTgCalls

from Emilia.config import Config
from Emilia.services.client_lifecycle import stop_client

LOGGER = logging.getLogger(__name__)

_SESSIONS_DIR = Path(Config.SESSION_DIRECTORY)


def _decode_session_string(session_string: str):
    n = len(session_string)
    padded = base64.urlsafe_b64decode(session_string + "=" * (-n % 4))
    if n in (Storage.SESSION_STRING_SIZE, Storage.SESSION_STRING_SIZE_64):
        fmt = (
            Storage.OLD_SESSION_STRING_FORMAT
            if n == Storage.SESSION_STRING_SIZE
            else Storage.OLD_SESSION_STRING_FORMAT_64
        )
        dc_id, test_mode, auth_key, user_id, is_bot = struct.unpack(fmt, padded)
        api_id = None
    else:
        dc_id, api_id, test_mode, auth_key, user_id, is_bot = struct.unpack(
            Storage.SESSION_STRING_FORMAT, padded
        )
    return dc_id, api_id, test_mode, auth_key, user_id, is_bot


def _provision_assistant_session(session_string: str, api_id: int) -> str:
    dc_id, str_api_id, test_mode, auth_key, user_id, is_bot = _decode_session_string(session_string)
    name = f"music_assistant_{user_id}"
    _SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    db_path = _SESSIONS_DIR / (name + SQLiteStorage.FILE_EXTENSION)

    if db_path.is_file():
        try:
            with closing(sqlite3.connect(str(db_path))) as con:
                row = con.execute("SELECT auth_key, user_id FROM sessions").fetchone()
            if row and row[0] == auth_key and row[1] == user_id:
                return name
        except sqlite3.DatabaseError:
            LOGGER.warning("Assistant session is unreadable; rebuilding it", exc_info=True)
        db_path.unlink()

    server_address = (TEST if test_mode else PROD)[dc_id]
    port = 80 if test_mode else 443
    con = sqlite3.connect(str(db_path))
    try:
        with con:
            con.executescript(SCHEMA)
            con.execute("INSERT INTO version VALUES (?)", (SQLiteStorage.VERSION,))
            # dc_id, server_address, port, api_id, test_mode, auth_key, date, user_id, is_bot.
            con.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    dc_id,
                    server_address,
                    port,
                    str_api_id or api_id,
                    1 if test_mode else 0,
                    auth_key,
                    0,
                    user_id,
                    1 if is_bot else 0,
                ),
            )
    finally:
        con.close()
    LOGGER.info("[Music] Provisioned persistent assistant session at %s", db_path)
    return name


def _build_assistant() -> Client:
    if not Config.SESSION_STRING:
        raise RuntimeError("SESSION_STRING is required for the music assistant but is empty.")
    name = _provision_assistant_session(Config.SESSION_STRING, Config.API_ID)
    return Client(name, api_id=Config.API_ID, api_hash=Config.API_HASH, workdir=str(_SESSIONS_DIR))


assistant = _build_assistant()
emilia_call = PyTgCalls(assistant)


async def shutdown_music():
    try:
        if emilia_call._is_running:
            calls = await asyncio.wait_for(emilia_call.calls, Config.CLONE_STOP_TIMEOUT)
            results = await asyncio.gather(
                *(
                    asyncio.wait_for(emilia_call.leave_call(chat_id), Config.CLONE_STOP_TIMEOUT)
                    for chat_id in calls
                ),
                return_exceptions=True,
            )
            if any(isinstance(result, Exception) for result in results):
                LOGGER.warning("Some music calls could not be left during shutdown")
    finally:
        await stop_client(assistant)
