import asyncio
import logging
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from Emilia.application import db, pgram
from Emilia.config import Config
from Emilia.database.backup import archive_database, complete_thread, dump_database
from Emilia.locales import tr
from Emilia.utils.tg_safe import flood_safe

LOGGER = logging.getLogger(__name__)
_LOCK = asyncio.Lock()


async def send() -> bool:
    async with _LOCK:
        directory = Path(Config.BACKUP_DIRECTORY)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        target = directory / f"backup_{datetime.now(UTC):%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.zip"
        sent = False
        try:
            with tempfile.TemporaryDirectory(dir=directory, prefix=".dump-") as temporary:
                manifest = await dump_database(db, Path(temporary))
                await complete_thread(archive_database, Path(temporary), target)
            count = sum(item["count"] for item in manifest["collections"])
            await flood_safe(
                lambda: pgram.send_document(
                    Config.BACKUP_CHANNEL_ID,
                    str(target),
                    caption=tr(
                        "backup.full_database_backup_collections_documents",
                        collections=len(manifest["collections"]),
                        count=count,
                    ),
                ),
                retries=5,
            )
            sent = True
            LOGGER.info("Full database backup uploaded")
            return True
        except Exception:
            LOGGER.exception("Database backup upload failed; archive retained")
            return False
        finally:
            if sent:
                target.unlink(missing_ok=True)
            retained = sorted(
                directory.glob("backup_*.zip"), key=lambda path: path.stat().st_mtime, reverse=True
            )
            for old in retained[5:]:
                old.unlink(missing_ok=True)
