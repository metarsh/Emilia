# restore script to restore a database into an empty database from archive

import argparse
import asyncio
import os
from pathlib import Path

from pymongo import AsyncMongoClient

from Emilia.database.backup import inspect_backup, restore_database


async def main(args):
    manifest = await asyncio.to_thread(inspect_backup, args.archive)
    print(
        f"Verified {len(manifest['collections'])} collections, {sum(item['count'] for item in manifest['collections'])} documents"
    )
    if not args.apply:
        return
    if not args.database or not args.uri:
        raise ValueError("--apply requires --database and MONGO_RESTORE_URL or --uri")
    async with AsyncMongoClient(args.uri, serverSelectionTimeoutMS=5000) as client:
        await restore_database(client[args.database], args.archive)
    print("Restoration complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--uri", default=os.environ.get("MONGO_RESTORE_URL"))
    parser.add_argument("--database")
    asyncio.run(main(parser.parse_args()))
