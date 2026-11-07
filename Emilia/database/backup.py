# daily backups of the database that goes to the log channel set by developer

import asyncio
import hashlib
import struct
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import bson
from bson import json_util


def _digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


async def dump_database(database, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    manifest = {"version": 1, "created_at": datetime.now(UTC).isoformat(), "collections": []}
    cursor = await database.list_collections()
    collections = [item async for item in cursor]
    if any(item["type"] != "collection" for item in collections):
        raise ValueError("This backup format requires regular collections")
    for item in sorted(collections, key=lambda item: item["name"]):
        name = item["name"]
        filename = hashlib.sha256(name.encode()).hexdigest() + ".bson"
        path = destination / filename
        count = 0
        chunk = bytearray()
        with path.open("wb") as output:
            async for document in database[name].find({}):
                chunk.extend(bson.BSON.encode(document))
                count += 1
                if len(chunk) >= 256 * 1024:
                    await complete_thread(output.write, bytes(chunk))
                    chunk.clear()
            if chunk:
                await complete_thread(output.write, bytes(chunk))
        cursor = await database[name].list_indexes()
        indexes = [dict(index) async for index in cursor]
        manifest["collections"].append(
            {
                "name": name,
                "file": filename,
                "count": count,
                "sha256": await complete_thread(_digest, path),
                "indexes": indexes,
                "options": item.get("options", {}),
            }
        )
    await complete_thread(
        (destination / "manifest.json").write_text, json_util.dumps(manifest), "utf-8"
    )
    return manifest


def archive_database(directory: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in directory.iterdir():
            archive.write(path, arcname=path.name)


async def complete_thread(function, *args):
    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        await asyncio.gather(worker, return_exceptions=True)
        raise


def documents(stream):
    while prefix := stream.read(4):
        if len(prefix) != 4:
            raise ValueError("Truncated BSON length")
        length = struct.unpack("<i", prefix)[0]
        if not 5 <= length <= 16 * 1024**2:
            raise ValueError("Invalid BSON document length")
        body = stream.read(length - 4)
        if len(body) != length - 4:
            raise ValueError("Truncated BSON document")
        yield bson.BSON(prefix + body).decode()


def inspect_backup(path, max_bytes=10 * 1024**3):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len({entry.filename for entry in entries}) != len(entries):
            raise ValueError("Duplicate archive entry")
        if sum(entry.file_size for entry in entries) > max_bytes:
            raise ValueError("Backup exceeds the configured size limit")
        if archive.getinfo("manifest.json").file_size > 10 * 1024**2:
            raise ValueError("Backup manifest is too large")
        manifest = json_util.loads(archive.read("manifest.json"))
        if manifest.get("version") != 1:
            raise ValueError("Unsupported backup version")
        names = set()
        expected = {"manifest.json"}
        for item in manifest["collections"]:
            name = item["name"]
            filename = hashlib.sha256(name.encode()).hexdigest() + ".bson"
            if name in names or item["file"] != filename:
                raise ValueError("Invalid collection manifest")
            names.add(name)
            expected.add(filename)
            with archive.open(filename) as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != item["sha256"]:
                    raise ValueError("Backup checksum failed")
            with archive.open(filename) as stream:
                if sum(1 for _ in documents(stream)) != item["count"]:
                    raise ValueError("Backup document count differs")
        if expected != {entry.filename for entry in entries}:
            raise ValueError("Unexpected archive entry")
        return manifest


async def restore_database(database, path):
    manifest = await complete_thread(inspect_backup, path)
    if await database.list_collection_names():
        raise ValueError("Restore requires an empty destination database")
    with zipfile.ZipFile(path) as archive:
        for item in manifest["collections"]:
            collection = await database.create_collection(item["name"], **item.get("options", {}))
            with archive.open(item["file"]) as stream:
                batch = []
                size = 0
                for document in documents(stream):
                    batch.append(document)
                    size += len(bson.BSON.encode(document))
                    if len(batch) >= 500 or size >= 8 * 1024**2:
                        await collection.insert_many(batch, bypass_document_validation=True)
                        batch.clear()
                        size = 0
                if batch:
                    await collection.insert_many(batch, bypass_document_validation=True)
            for index in item["indexes"]:
                if index["name"] == "_id_":
                    continue
                options = {
                    key: value for key, value in index.items() if key not in {"key", "v", "ns"}
                }
                keys = []
                for field, direction in index["key"].items():
                    if field == "_fts" and direction == "text":
                        keys.extend((name, "text") for name in index["weights"])
                    elif field != "_ftsx" or index["key"].get("_fts") != "text":
                        keys.append((field, direction))
                await collection.create_index(keys, **options)
    return manifest
