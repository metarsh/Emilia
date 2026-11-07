import asyncio
import json
import os
import random
import tempfile
import time
from dataclasses import dataclass, field
from functools import wraps
from io import BytesIO
from typing import Any

from aiohttp import ClientError
from groq import APIStatusError, AsyncGroq
from pymongo.errors import DuplicateKeyError, PyMongoError
from pyrogram.enums import ChatAction, ChatType, MessageEntityType

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.custom_filter import command, listen
from Emilia.database.common import atomic_upsert
from Emilia.locales import tr
from Emilia.utils.chat_status import is_user_admin
from Emilia.utils.command_help import reply_usage
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.errors import report_error
from Emilia.utils.http import post as async_post
from Emilia.utils.message_actor import actor_id, actor_user
from Emilia.utils.message_content import utf16_length
from Emilia.utils.process import run_process
from Emilia.utils.tasks import finish_cleanup, spawn

MODEL = Config.CHATBOT_MODEL
MEMORY_MODEL = Config.CHATBOT_MEMORY_MODEL
DEFAULT_TEMPERATURE = 0.8
DEFAULT_MAX_TOKENS = 768
MAX_HISTORY = 50
MAX_MEMORY_LEN = 1500
MAX_SESSIONS = Config.CHATBOT_MAX_SESSIONS
SESSION_TTL_SECONDS = Config.CHATBOT_SESSION_TTL

# Cartesia sonic-3 — TTS for Hindi/Hinglish voice notes
# API: POST https://api.cartesia.ai/tts/bytes (returns raw audio bytes)
CARTESIA_TTS_URL = "https://api.cartesia.ai/tts/bytes"
CARTESIA_API_VERSION = "2025-04-16"
CARTESIA_MODEL = Config.CARTESIA_MODEL
# radha <3
CARTESIA_VOICE_ID = Config.CARTESIA_VOICE_ID


# clients
groq_client = AsyncGroq(api_key=Config.GROQ_API_KEY, timeout=30.0, max_retries=2)

voice_enabled = bool(Config.CARTESIA_API_KEY)
if not voice_enabled:
    LOGGER.warning("[Voice] CARTESIA_API_KEY missing. Voice disabled.")

chatbotdb = db.chatbotto
convodb = db.gemini_convos


# tools

VOICE_TOOL = {
    "type": "function",
    "function": {
        "name": "prepare_voice_note",
        "description": "Prepare a voice reply for the application to synthesize and deliver.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": (
                        tr("chatbot.what_say_written_entirely_hindi_devanagari_script_no")
                    ),
                },
            },
            "required": ["text"],
        },
    },
}

TOOLS = [VOICE_TOOL] if voice_enabled else []


# data types


@dataclass
class ChatResponse:
    type: str  # "text" or "voice"
    text: str | None = None  # plain text reply
    voice_text: str | None = None  # text to speak (Hindi Devanagari)


@dataclass
class UserSession:
    user_id: int
    chat: "GroqChatSession | None" = None
    last_used: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    memory_tasks: set[asyncio.Task] = field(default_factory=set)
    active_requests: int = 0


user_chats: dict[int, UserSession] = {}


class GroqChatSession:
    def __init__(self, system_instruction: str):
        self._send_lock = asyncio.Lock()
        self.history: list[dict[str, Any]] = []
        if system_instruction:
            self.history.append({"role": "system", "content": system_instruction})

    def _trim_history(self):
        if len(self.history) <= MAX_HISTORY:
            return
        system = self.history[0] if self.history[0]["role"] == "system" else None
        rest = [m for m in self.history if m["role"] != "system"]
        keep = MAX_HISTORY - (1 if system else 0)
        rest = rest[-keep:]
        while rest and rest[0]["role"] != "user":
            rest.pop(0)
        self.history = ([system] if system else []) + rest

    async def send(self, content: str) -> ChatResponse:
        async with self._send_lock:
            return await self._send(content)

    async def _send(self, content: str) -> ChatResponse:
        previous_history = self.history.copy()
        self.history.append({"role": "user", "content": content})
        self._trim_history()

        try:
            kwargs = {
                "model": MODEL,
                "messages": self.history,
                "temperature": DEFAULT_TEMPERATURE,
                "max_tokens": DEFAULT_MAX_TOKENS,
                "reasoning_effort": "none",
            }
            if TOOLS:
                kwargs["tools"] = TOOLS
                kwargs["tool_choice"] = "auto"

            completion = await groq_client.chat.completions.create(**kwargs)
            msg = completion.choices[0].message

            if msg.tool_calls:
                tc = msg.tool_calls[0]
                if tc.function.name == "prepare_voice_note":
                    try:
                        args = json.loads(tc.function.arguments)
                        if not isinstance(args, dict) or not isinstance(args.get("text"), str):
                            raise ValueError("Invalid voice tool arguments")
                        voice_text = args["text"].strip()
                        if not voice_text:
                            raise ValueError("Voice text is empty")
                    except (ValueError, TypeError):
                        fallback = msg.content or tr("chatbot.m_sorry_don_t_have_answer")
                        self.history.append({"role": "assistant", "content": fallback})
                        self._trim_history()
                        return ChatResponse(type="text", text=fallback)

                    self.history.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": tc.id,
                                    "type": "function",
                                    "function": {
                                        "name": tc.function.name,
                                        "arguments": tc.function.arguments,
                                    },
                                }
                            ],
                        }
                    )
                    self.history.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": "Voice text prepared for delivery.",
                        }
                    )

                    self._trim_history()
                    return ChatResponse(
                        type="voice",
                        voice_text=voice_text,
                    )

            response_text = msg.content or ""
            self.history.append({"role": "assistant", "content": response_text})
            self._trim_history()
            return ChatResponse(type="text", text=response_text)

        except BaseException:
            self.history = previous_history
            raise


# voice generation


async def generate_voice_note(text: str) -> str | None:
    """TTS via Cartesia sonic-3 -> raw WAV bytes -> ffmpeg -> OGG Opus for Telegram."""
    if not voice_enabled:
        return None

    ogg_path: str | None = None
    wav_path: str | None = None

    try:
        payload = {
            "model_id": CARTESIA_MODEL,
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": CARTESIA_VOICE_ID,
            },
            "output_format": {
                "container": "wav",
                "encoding": "pcm_f32le",
                "sample_rate": 44100,
            },
            "speed": "normal",
            "generation_config": {
                "speed": 1,
                "volume": 1,
            },
        }

        headers = {
            "Cartesia-Version": CARTESIA_API_VERSION,
            "X-API-Key": Config.CARTESIA_API_KEY,
            "Content-Type": "application/json",
        }

        resp = await async_post(CARTESIA_TTS_URL, json=payload, headers=headers, timeout=30)
        if resp.status != 200:
            LOGGER.error(f"[Voice] Cartesia API {resp.status}: {resp.text[:300]}")
            return None
        audio_bytes = resp.content

        if not audio_bytes:
            LOGGER.error("[Voice] Cartesia returned empty audio")
            return None

        # Write WAV to temp file
        wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
        with os.fdopen(wav_fd, "wb") as f:
            f.write(audio_bytes)

        # Convert WAV → OGG Opus for Telegram voice note
        ogg_fd, ogg_path = tempfile.mkstemp(suffix=".ogg")
        os.close(ogg_fd)

        result = await run_process(
            "ffmpeg",
            "-y",
            "-i",
            wav_path,
            "-c:a",
            "libopus",
            "-b:a",
            "64k",
            "-vbr",
            "on",
            "-compression_level",
            "10",
            "-application",
            "voip",
            ogg_path,
        )

        if result.returncode != 0:
            LOGGER.error("[Voice] ffmpeg conversion failed")
            _safe_remove(ogg_path)
            ogg_path = None
            return None

        return ogg_path

    except asyncio.CancelledError:
        _safe_remove(ogg_path)
        raise

    except TimeoutError:
        LOGGER.error("[Voice] Cartesia API request timed out")
        _safe_remove(ogg_path)
        ogg_path = None
        return None

    except (ClientError, OSError, ValueError) as e:
        LOGGER.error(f"[Voice] Generation failed: {e}")
        _safe_remove(ogg_path)
        ogg_path = None
        return None

    finally:
        _safe_remove(wav_path)


def _safe_remove(path: str | None):
    if path:
        try:
            os.remove(path)
        except OSError:
            pass


# helpers


def trimMemory(text: str) -> str:
    return (text.strip())[-MAX_MEMORY_LEN:] if text else ""


def purgeSessions(now: float = None):
    if not user_chats:
        return
    now = time.monotonic() if now is None else now
    idle = {
        uid: state
        for uid, state in user_chats.items()
        if not state.active_requests and not state.lock.locked() and not state.memory_tasks
    }
    for uid, state in idle.items():
        if now - state.last_used > SESSION_TTL_SECONDS:
            user_chats.pop(uid, None)

    for uid in sorted(idle, key=lambda uid: idle[uid].last_used):
        if len(user_chats) <= MAX_SESSIONS:
            break
        user_chats.pop(uid, None)


def _user_session(user_id: int) -> UserSession:
    state = user_chats.get(user_id)
    if state is None:
        state = UserSession(user_id)
        user_chats[user_id] = state
    state.last_used = time.monotonic()
    return state


async def getOrCreateChat(state: UserSession) -> GroqChatSession:
    async with state.lock:
        if state.chat is None:
            doc = await convodb.find_one({"user_id": state.user_id})
            memory = doc.get("memory") if doc else None
            system = PERSONA_DETAILS
            if memory:
                system += tr("chatbot.known_about_user", memory=memory)
            state.chat = GroqChatSession(system)
        return state.chat


async def updateUserMemory(
    state: UserSession, chat: GroqChatSession, user_text: str, bot_text: str
):
    try:
        if state.chat is not chat:
            return
        prompt = tr(
            "chatbot.extract_3_user_facts_preferences_name_style_from",
            user_text=user_text,
            bot_text=bot_text,
        )
        completion = await groq_client.chat.completions.create(
            model=MEMORY_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=128,
            reasoning_effort="low",
        )
        facts = (completion.choices[0].message.content or "").strip()
        if not facts:
            return

        async with state.lock:
            if state.chat is not chat:
                return
            for _ in range(4):
                doc = await convodb.find_one({"user_id": state.user_id})
                existing = (doc.get("memory") if doc else "") or ""
                lines = [
                    line.strip(" •-\t")
                    for line in (existing + "\n" + facts).splitlines()
                    if line.strip()
                ]
                merged = trimMemory("\n".join(dict.fromkeys(lines)))
                if doc is None:
                    try:
                        await convodb.insert_one({"user_id": state.user_id, "memory": merged})
                        return
                    except DuplicateKeyError:
                        continue
                result = await convodb.update_one(
                    {"_id": doc["_id"], "memory": doc.get("memory")}, {"$set": {"memory": merged}}
                )
                if result.matched_count:
                    return
            raise RuntimeError("Chatbot memory changed repeatedly during update")
    except Exception:
        LOGGER.warning("Chatbot memory update failed", exc_info=True)


# handlers


async def handleChatRequest(message, query: str) -> ChatResponse | None:
    user_id = message.from_user.id if message.from_user else None
    if user_id is None:
        return None
    state = _user_session(user_id)
    state.active_requests += 1
    try:
        chat = await getOrCreateChat(state)
        response = await chat.send(query)
        if response:
            mem_text = response.text or response.voice_text or ""
            if mem_text and state.chat is chat:
                task = spawn(
                    updateUserMemory(state, chat, query, mem_text),
                    name="update_user_memory",
                )
                state.memory_tasks.add(task)
                task.add_done_callback(state.memory_tasks.discard)
        return response

    except APIStatusError as e:
        await report_error("chatbot.api", e, user_id=user_id, status=e.status_code)
    except Exception as e:
        await report_error("chatbot", e, user_id=user_id)
    finally:
        state.active_requests -= 1
        state.last_used = time.monotonic()
        purgeSessions()

    return None


def _main_bot_only(handler):
    @wraps(handler)
    async def wrapped(client, message, *args, **kwargs):
        if getattr(client, "is_clone", False):
            await message.reply_text(tr("chatbot.main_bot_only"))
            return
        return await handler(client, message, *args, **kwargs)

    return wrapped


@command("chatbot")
@_main_bot_only
@anonadmin_checker
async def chatbotcheck(client, message):
    if message.chat.type in (
        ChatType.GROUP,
        ChatType.SUPERGROUP,
    ) and not await is_user_admin(
        message, user_id=actor_id(message) if actor_user(message) else None, silent=True
    ):
        return

    query = message.text.split(" ", 1)
    if len(query) == 1:
        await reply_usage(message)
        return

    cmd = query[1].lower()
    if cmd in ("enable", "on", "yes"):
        await atomic_upsert(
            chatbotdb, {"chat_id": message.chat.id}, {"$set": {"chat_id": message.chat.id}}
        )
        await message.reply_text(tr("chatbot.chatbot_enabled"))
    elif cmd in ("disable", "off", "no"):
        await chatbotdb.delete_one({"chat_id": message.chat.id})
        await message.reply_text(tr("chatbot.chatbot_disabled"))
    else:
        await message.reply_text(tr("chatbot.invalid_argument_use_enable_or_disable"))


@command("reset")
@_main_bot_only
async def reset_conversation(client, message):
    if message.from_user is None:
        return await message.reply_text(tr("chatbot.reset_requires_user"))
    state = _user_session(message.from_user.id)
    try:
        async with state.lock:
            previous = state.chat
            state.chat = None
            try:
                pending = tuple(state.memory_tasks)
                for task in pending:
                    task.cancel()
                await finish_cleanup(asyncio.gather(*pending, return_exceptions=True))
                await convodb.delete_one({"user_id": state.user_id})
            except BaseException:
                state.chat = previous
                raise
    except PyMongoError:
        LOGGER.exception("Chatbot reset failed for %s", state.user_id)
        await message.reply_text(tr("chatbot.failed_to_reset_conversation"))
        return
    await message.reply_text(tr("chatbot.conversation_reset"))


@listen()
async def message_handler(client, message):
    if getattr(client, "is_clone", False):
        return
    purgeSessions()

    if message.service or message.from_user is None or message.from_user.is_bot:
        return

    if message.entities:
        for entity in message.entities:
            if entity.type in (
                MessageEntityType.BOT_COMMAND,
                MessageEntityType.MENTION,
                MessageEntityType.TEXT_MENTION,
            ):
                return
            if (message.text or "").startswith("!"):
                return

    if not message.reply_to_message_id:
        return

    if not await chatbotdb.find_one({"chat_id": message.chat.id}):
        return

    reply = message.reply_to_message
    if not reply or not reply.from_user or reply.from_user.id != Config.BOT_ID:
        return

    query = await getQueryFromEvent(message)
    if not query:
        return

    await client.send_chat_action(message.chat.id, ChatAction.TYPING)
    response = await handleChatRequest(message, query)

    if not response:
        await message.reply_text(random.choice(RANDOM_RESPONSES))
        return

    if response.type == "voice" and response.voice_text:
        ogg_path = None
        try:
            await client.send_chat_action(message.chat.id, ChatAction.RECORD_AUDIO)
            ogg_path = await generate_voice_note(response.voice_text)

            if ogg_path:
                await message.reply_voice(ogg_path)
            else:
                await sendResponse(message, response.voice_text)
        finally:
            _safe_remove(ogg_path)
        return

    await sendResponse(message, response.text or "")


# utils


async def getQueryFromEvent(message) -> str | None:
    if getattr(message, "document", None):
        return await readFileText(message)
    return message.text


async def readFileText(message) -> str | None:
    if message.document.file_size > 1_000_000:
        await message.reply_text(tr("chatbot.file_too_large_max_1mb"))
        return None
    async with asyncio.timeout(60):
        document = await message.download(in_memory=True)
    if document is None:
        return None
    try:
        if document.getbuffer().nbytes > 1_000_000:
            await message.reply_text(tr("chatbot.file_too_large_max_1mb"))
            return None
        return document.getvalue().decode("utf-8")
    except UnicodeDecodeError:
        return None
    finally:
        document.close()


async def sendResponse(message, response: str):
    if utf16_length(response) > 4096:
        with BytesIO(response.encode("utf-8")) as document:
            document.name = "response.txt"
            await message.reply_document(document)
    else:
        await message.reply_text(response)


# persona

PERSONA_DETAILS = tr("chatbot.you_re_bot_name_from_re_zero")


async def shutdown_chatbot():
    user_chats.clear()
    await groq_client.close()


RANDOM_RESPONSES = [
    tr("chatbot.m_sorry_don_t_have_answer"),
    tr("chatbot.m_not_sure_can_please_rephrase"),
    tr("chatbot.m_still_learning"),
    tr("chatbot.wish_could_help_but_don_t_have_info"),
    tr("chatbot.hmm_s_tough_one"),
    tr("chatbot.m_afraid_can_t_assist"),
    tr("chatbot.m_here_chat_but_might_not_have_answer"),
]
