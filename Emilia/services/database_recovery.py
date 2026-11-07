import asyncio

from Emilia.application import LOGGER
from Emilia.database.federations import recover_deletions
from Emilia.database.levels import recover_reputation
from Emilia.database.playlists import recover_mutations


async def database_recovery_loop():
    while True:
        for recover in (recover_deletions, recover_mutations, recover_reputation):
            try:
                await recover()
            except Exception:
                LOGGER.exception("Database mutation recovery failed")
        await asyncio.sleep(60)
