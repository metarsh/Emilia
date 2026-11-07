import re
from os import getenv
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv(
    getenv("ENV_FILE", str(Path(__file__).resolve().parents[1] / ".env")),
    override=False,
    interpolate=False,
)


def _env_int(name: str) -> int:
    try:
        return int(getenv(name) or 0)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


class Config:
    # necessary
    TOKEN = getenv("TOKEN", "").strip()
    API_ID = _env_int("API_ID")
    API_HASH = getenv("API_HASH", "").strip()
    OWNER_ID = _env_int("OWNER_ID")
    SESSION_STRING = getenv("SESSION_STRING", "").strip()
    BACKUP_CHANNEL_ID = _env_int("BACKUP_CHANNEL_ID")
    EVENT_LOGS = _env_int("EVENT_LOGS")
    MONGO_DB_URL = getenv("MONGO_DB_URL", "mongodb://localhost:27017")
    REDIS_URL = getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_PASSWORD = getenv("REDIS_PASSWORD") or None
    DEV_USERS = sorted(
        {int(user) for user in getenv("DEV_USERS", "").replace(",", " ").split()} | {OWNER_ID}
    )
    BOT_ID = int(TOKEN.partition(":")[0]) if TOKEN.partition(":")[0].isdigit() else 0
    BOT_USERNAME = ""  # Filled from Telegram after the main bot starts.

    # optionals
    GROQ_API_KEY = getenv("GROQ_API_KEY", "").strip()
    BOT_NAME = getenv("BOT_NAME", "Emilia")
    SUPPORT_CHAT = getenv("SUPPORT_CHAT", "").removeprefix("@")
    UPDATE_CHANNEL = getenv("UPDATE_CHANNEL", "").removeprefix("@")
    START_PIC = getenv("START_PIC", "")
    DONATION_URL = getenv("DONATION_URL", "https://t.me/Elf_Robot/donation")
    CARTESIA_API_KEY = getenv("CARTESIA_API_KEY", "")
    WALL_API = getenv("WALL_API", "")
    SAUCENAO_API_KEY = getenv("SAUCENAO_API_KEY", "")
    GIPHY_API_KEY = getenv("GIPHY_API_KEY", "")
    CAS_API_KEY = getenv("CAS_API_KEY", "").strip()
    ANILIST_CLIENT = _env_int("ANILIST_CLIENT")
    ANILIST_SECRET = getenv("ANILIST_SECRET", "")
    ZIPLINE_URL = getenv("ZIPLINE_URL", "")
    ZIPLINE_AUTH_URL = getenv("ZIPLINE_AUTH_URL", "") or ZIPLINE_URL
    ZIPLINE_USERNAME = getenv("ZIPLINE_USERNAME", "")
    ZIPLINE_PASSWORD = getenv("ZIPLINE_PASSWORD", "")
    ZIPLINE_TOKEN = getenv("ZIPLINE_TOKEN", "")
    AD_URL = getenv("AD_URL", "")
    ADS_ENABLED = bool(AD_URL)

    # fixed, change them if you know what you are doing
    SOURCE_URL = "https://github.com/metarsh/Emilia"
    HTTP_USER_AGENT = f"{BOT_NAME}/1.0 ({SOURCE_URL})"
    QUOTE_API_URL = "http://quote-api:3000"
    VANITAS_API_URL = "https://vanitas-smjr.onrender.com"
    TRANSLATE_API_URL = "https://translate.googleapis.com/translate_a/single"
    CARBON_API_URL = "https://carbonara.solopov.dev/api/cook"
    ANILIST_REDIRECT_URL = "https://anilist.co/api/v2/oauth/pin"
    CHATBOT_MODEL = "qwen/qwen3.8-27b"
    CHATBOT_MEMORY_MODEL = "openai/gpt-oss-20b"
    CARTESIA_MODEL = "sonic-3"
    CARTESIA_VOICE_ID = "c6fabd03-334e-42e4-b21d-49b1b58faab7"
    LANGUAGE = "en"
    TIMEZONE = "Asia/Kolkata"
    TRIGGERS = ("/", "!")

    # let's not change them without proper reason
    STATE_DIR = "state"
    SESSION_DIRECTORY = "sessions"
    TEMP_DOWNLOAD_DIRECTORY = "downloads/"
    DOWN_PATH = "downloads/anime/"
    COOKIES_FILE = "www.youtube.com_cookies.txt"
    FONT_DIRECTORY = str(Path(__file__).resolve().parent / "assets/fonts")
    LOG_FILE = f"{STATE_DIR}/log.txt"
    BACKUP_DIRECTORY = f"{STATE_DIR}/backups"
    MONGO_DATABASE = "Emilia"
    MONGO_MAX_POOL_SIZE = 50
    REDIS_MAX_CONNECTIONS = 50
    CACHE_NAMESPACE = MONGO_DATABASE
    CACHE_MAX_L1_ENTRIES = 10000
    CACHE_QUERY_MAX_ENTRIES = 1000
    CACHE_QUERY_TTL = 900
    HTTP_MAX_RESPONSE_BYTES = 20 * 1024**2
    HTTP_CONNECTION_LIMIT = 100
    HTTP_PER_HOST_LIMIT = 20
    HTTP_RETRY_MAX_DELAY = 30
    MAX_DOWNLOAD_BYTES = 50 * 1024**2
    MAX_ARCHIVE_BYTES = 200 * 1024**2
    MAX_ARCHIVE_FILES = 100
    MAX_COMPRESSION_RATIO = 100
    WRITE_BUFFER_MAX_ENTRIES = 10000
    WRITE_BUFFER_BATCH_SIZE = 500
    WRITE_BUFFER_SHUTDOWN_TIMEOUT = 30
    UPLOAD_TIMEOUT = 60
    OPERATOR_TIMEOUT = 30
    RATE_LIMIT_GENERAL = (3, 5)
    RATE_LIMIT_HEAVY = (1, 5)
    RATE_LIMIT_SUPER_HEAVY = (1, 30)
    VANITAS_CACHE_TTL = 60
    QUOTE_MAX_VOTERS = 10000
    CARBON_MAX_CHARACTERS = 10000
    MUSIC_MAX_QUEUE_TRACKS = 1000
    MUSIC_METADATA_TIMEOUT = 120
    MUSIC_DOWNLOAD_TIMEOUT = 900
    MUSIC_MAX_DOWNLOAD_BYTES = 512 * 1024**2
    MUSIC_DOWNLOAD_MAX_AGE_HOURS = 168
    MUSIC_DOWNLOAD_CACHE_BYTES = 25 * 1024**3
    PLAYLIST_MAX_SONGS = 1000
    PLAYLIST_MAX_PER_USER = 100
    CHATBOT_MAX_SESSIONS = 500
    CHATBOT_SESSION_TTL = 3600
    FEDERATION_MAX_SUBSCRIPTIONS = 5
    LEVEL_XP_BASE = 50
    LEVEL_XP_MULTIPLIER = 1.3
    LEVEL_MESSAGE_COOLDOWN = 5
    LEVEL_EVENT_MULTIPLIER = 1
    CLONE_LIMIT = 150
    CLONES_PER_USER = 2
    CLONE_PREMIUM_ENABLED = True
    CLONE_PREMIUM_STARS = 100
    CLONE_START_TIMEOUT = 60
    CLONE_STOP_TIMEOUT = 20
    CLONE_HEALTH_INTERVAL = 600
    CLONE_START_CONCURRENCY = 5

    @classmethod
    def validate(cls) -> None:
        required = (
            "TOKEN",
            "API_ID",
            "API_HASH",
            "OWNER_ID",
            "SESSION_STRING",
            "BACKUP_CHANNEL_ID",
        )
        missing = [name for name in required if not getattr(cls, name)]
        if missing:
            raise ValueError("Missing required settings: " + ", ".join(missing))
        if not re.fullmatch(r"[1-9]\d*:[A-Za-z0-9_-]+", cls.TOKEN):
            raise ValueError("TOKEN must be a Telegram bot token")
        if cls.API_ID <= 0 or cls.OWNER_ID <= 0:
            raise ValueError("API_ID and OWNER_ID must be positive Telegram IDs")
        if cls.BACKUP_CHANNEL_ID >= 0:
            raise ValueError("BACKUP_CHANNEL_ID must be a private Telegram channel ID")
        if not cls.MONGO_DB_URL.startswith(("mongodb://", "mongodb+srv://")):
            raise ValueError("MONGO_DB_URL must be a MongoDB connection URI")
        if not cls.REDIS_URL.startswith(("redis://", "rediss://")):
            raise ValueError("REDIS_URL must be a Redis connection URI")
        cls.BOT_ID = int(cls.TOKEN.partition(":")[0])
        ZoneInfo(cls.TIMEZONE)
