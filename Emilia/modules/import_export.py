import asyncio
import io

import orjson
from bson import ObjectId
from pyrogram.enums import ButtonStyle, ChatType, MessageEntityType

from Emilia.application import LOGGER, db
from Emilia.config import Config
from Emilia.custom_filter import callbackquery, command
from Emilia.database.common import atomic_upsert
from Emilia.database.locks import invalidate_locks
from Emilia.locales import tr
from Emilia.utils.cache import blocklist_cache
from Emilia.utils.chat_context import effective_chat, effective_chat_id
from Emilia.utils.chat_status import is_chat_owner
from Emilia.utils.command_help import reply_usage
from Emilia.utils.confirmation import authorize_chat_confirmation, send_confirmation
from Emilia.utils.decorators import anonadmin_checker
from Emilia.utils.menu_guard import CallbackAccess
from Emilia.utils.message_content import formatted_text, text_value, utf16_length
from Emilia.utils.saved_message import SavedMessageType

MAX_IMPORT_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def default(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    raise TypeError


collections = {
    "blocklists": db["blocklists"],
    "disable": db["disable"],
    "filters": db["filters"],
    "locks": db["locks"],
    "notes": db["notes"],
    "rules": db["rules"],
    "warnings": db["warn_settings"],
    "welcome": db["welcome"],
}

CAPTCHA_SETTINGS = {"_captcha", "captcha_mode", "captcha_text", "captcha_kick_time"}


def _portable_settings(section, value):
    result = {key: item for key, item in value.items() if key not in {"_id", "chat_id"}}
    if section == "welcome":
        result.pop("clean_welcome_message", None)
        if "captcha" in result:
            result["captcha"] = {
                key: item for key, item in result["captcha"].items() if key in CAPTCHA_SETTINGS
            }
            if not result["captcha"]:
                result.pop("captcha")
    return result


def _validate_text(value):
    if value is None:
        return
    if not isinstance(value, dict) or not isinstance(value.get("text"), str):
        raise ValueError("Invalid saved message text")
    if not isinstance(value.get("entities", []), list):
        raise ValueError("Invalid saved message entities")
    try:
        native = formatted_text(value)
        size = utf16_length(native.text)
        encoded = native.text.encode("utf-16-le")
        for entity in native.entities:
            if (
                type(entity.offset) is not int
                or type(entity.length) is not int
                or entity.offset < 0
                or entity.length < 1
                or entity.offset + entity.length > size
            ):
                raise ValueError("Invalid saved message entity range")
            for boundary in (entity.offset, entity.offset + entity.length):
                if (
                    boundary < size
                    and 0xDC00
                    <= int.from_bytes(encoded[boundary * 2 : boundary * 2 + 2], "little")
                    <= 0xDFFF
                ):
                    raise ValueError("Saved entity splits a Unicode character")
            if entity.url is not None and not isinstance(entity.url, str):
                raise ValueError("Invalid saved entity URL")
            if entity.type is MessageEntityType.TEXT_LINK and not entity.url:
                raise ValueError("Saved text links require a URL")
            if entity.user is not None and (
                type(entity.user.id) is not int or not 0 < entity.user.id < 2**63
            ):
                raise ValueError("Invalid saved entity user")
            if entity.type is MessageEntityType.TEXT_MENTION and entity.user is None:
                raise ValueError("Saved mentions require a user")
            if entity.type is MessageEntityType.CUSTOM_EMOJI and (
                not isinstance(entity.custom_emoji_id, str)
                or not entity.custom_emoji_id.isascii()
                or not entity.custom_emoji_id.isdigit()
            ):
                raise ValueError("Invalid saved custom emoji")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Invalid saved message entities") from exc


def _validate_saved_message(value, *, allow_empty=False):
    if not isinstance(value, dict):
        raise ValueError("Invalid saved message")
    if allow_empty and not value:
        return
    if (
        "content" in value
        and value["content"] is not None
        and not isinstance(value["content"], str)
    ):
        raise ValueError("Invalid saved media ID")
    if not isinstance(value.get("text"), dict):
        raise ValueError("Saved messages require a text/entity record")
    _validate_text(value["text"])
    if type(value.get("data_type")) is not int:
        raise ValueError("Invalid saved media type")
    kind = SavedMessageType(value["data_type"])
    if kind is SavedMessageType.text:
        if not text_value(value.get("text")).strip():
            raise ValueError("Saved text messages must contain text")
    elif not isinstance(value.get("content"), str) or not value["content"].strip():
        raise ValueError("Saved media messages require a file ID")


def _validate_settings(settings):
    bool_fields = {
        "blocklists": ("blocklistdelete",),
        "disable": ("disabledel",),
        "locks": ("lockwarns",),
        "notes": ("private_note",),
        "rules": ("private_note",),
        "welcome": (
            "welcome",
            "goodbye",
            "clean_service",
            "clean_welcome",
            "reCaptcha",
            "rule_captcha",
        ),
    }
    list_fields = {
        "blocklists": ("blocklist_text",),
        "disable": ("disabled_items",),
        "filters": ("filters",),
        "locks": ("locked", "allow_list"),
        "notes": ("notes",),
    }
    for section, value in settings.items():
        if section not in collections:
            continue
        if not isinstance(value, dict):
            raise ValueError("Settings sections must be objects")
        pending = [value]
        while pending:
            item = pending.pop()
            if isinstance(item, dict):
                if any(
                    not field or field.startswith("$") or "." in field or "\x00" in field
                    for field in item
                ):
                    raise ValueError("Invalid settings fields")
                pending.extend(item.values())
            elif isinstance(item, list):
                pending.extend(item)
            elif type(item) is int and not -(2**63) <= item < 2**63:
                raise ValueError("Settings integers must fit BSON")
        for field in bool_fields.get(section, ()):
            if field in value and type(value[field]) is not bool:
                raise ValueError("Settings flags must be booleans")
        for field in list_fields.get(section, ()):
            if field in value and not isinstance(value[field], list):
                raise ValueError("Settings lists must be arrays")
        if section == "disable" and any(
            not isinstance(name, str) or not name for name in value.get("disabled_items", [])
        ):
            raise ValueError("Disabled commands must be names")
        if section == "locks":
            from Emilia.modules.locks.lock_map import LocksMap

            for lock in value.get("locked", []):
                if type(lock) is not int:
                    raise ValueError("Invalid lock type")
                LocksMap(lock)
            if any(
                not isinstance(item, str)
                and (type(item) is not int or not -(2**63) <= item < 2**63)
                for item in value.get("allow_list", [])
            ):
                raise ValueError("Invalid allowlist entry")
        if section in {"notes", "filters", "blocklists"}:
            array = "blocklist_text" if section == "blocklists" else section
            name = {"notes": "note_name", "filters": "filter_name", "blocklists": "blocklist_text"}[
                section
            ]
            for entry in value.get(array, []):
                if (
                    not isinstance(entry, dict)
                    or not isinstance(entry.get(name), str)
                    or not entry[name].strip()
                ):
                    raise ValueError("Saved entries must have names")
                if section == "blocklists":
                    if entry.get("blocklist_reason") is not None and not isinstance(
                        entry["blocklist_reason"], str
                    ):
                        raise ValueError("Invalid blocklist reason")
                else:
                    _validate_saved_message(entry)
                    if "reply_to_sender" in entry and type(entry["reply_to_sender"]) is not bool:
                        raise ValueError("Invalid filter reply flag")
        for field in ("warn_mode", "blocklist_mode"):
            mode = value.get(field)
            if mode is not None:
                time_field = "warn_time" if field == "warn_mode" else "blocklist_time"
                maximum = 5 if field == "warn_mode" else 7
                if (
                    not isinstance(mode, dict)
                    or type(mode.get(field, 1)) is not int
                    or not 1 <= mode.get(field, 1) <= maximum
                ):
                    raise ValueError("Invalid moderation mode")
                duration = mode.get(time_field)
                if duration is not None and (
                    type(duration) is not int or not 0 < duration < 366 * 86400
                ):
                    raise ValueError("Invalid moderation duration")
                if mode.get(field, 1) in {maximum - 1, maximum} and duration is None:
                    raise ValueError("Timed moderation requires a duration")
        if "warn_limit" in value and (
            type(value["warn_limit"]) is not int or value["warn_limit"] < 1
        ):
            raise ValueError("Invalid warning limit")
        if section == "rules":
            _validate_text(value.get("rules"))
            if "button_text" in value and not isinstance(value["button_text"], str):
                raise ValueError("Invalid rules button")
        if section == "welcome":
            for field in ("welcome_message", "goodbye_message"):
                if field in value:
                    _validate_saved_message(value[field], allow_empty=True)
            if "captcha" in value:
                captcha = value["captcha"]
                if not isinstance(captcha, dict) or (
                    "_captcha" in captcha and type(captcha["_captcha"]) is not bool
                ):
                    raise ValueError("Invalid CAPTCHA settings")
                if captcha.get("captcha_mode", "button") not in {"button", "text", "math"}:
                    raise ValueError("Invalid CAPTCHA mode")
                if captcha.get("captcha_text") is not None and not isinstance(
                    captcha["captcha_text"], str
                ):
                    raise ValueError("Invalid CAPTCHA button text")
                if captcha.get("captcha_kick_time") is not None and type(
                    captcha["captcha_kick_time"]
                ) not in {int, str}:
                    raise ValueError("Invalid CAPTCHA timeout")


async def _resolve_owner_chat(message):
    """Resolve the target chat_id for an export/import/reset action and
    verify the caller owns it. Returns chat_id, or None after replying with
    an error (caller should just `return` in that case)."""
    chat_id = effective_chat_id(message)
    if effective_chat(message).type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await message.reply_text(tr("errors.group_only"))
        return None

    if not await is_chat_owner(message, chat_id=chat_id, silent=False):
        return None

    return chat_id


@command(
    "export", rate_limit=Config.RATE_LIMIT_SUPER_HEAVY, chat_scope="group", allow_connected=True
)
@anonadmin_checker(owner_only=True)
async def export_settings(client, message):
    chat_id = await _resolve_owner_chat(message)
    if chat_id is None:
        return

    args = message.text.split()[1:]

    exported_data = {}
    keys = args if args else collections.keys()
    for key in keys:
        collection = collections.get(key)
        if collection is None:
            continue
        settings = await collection.find_one({"chat_id": chat_id})
        if settings:
            portable = _portable_settings(key, settings)
            if portable:
                exported_data[key] = portable

    if not exported_data:
        await message.reply_text(tr("import_export.no_settings_found"))
        return

    settings_json = orjson.dumps(exported_data, option=orjson.OPT_INDENT_2, default=default)
    with io.BytesIO(settings_json) as buf:
        buf.name = f"chat_settings_{chat_id}.json"
        await message.reply_document(
            buf,
            caption=tr(
                "import_export.exported_section_s",
                exported_data=", ".join(exported_data.keys()),
                exported_data_2=len(exported_data),
            ),
        )


@command(
    "import", rate_limit=Config.RATE_LIMIT_SUPER_HEAVY, chat_scope="group", allow_connected=True
)
@anonadmin_checker(owner_only=True)
async def import_settings(client, message):
    chat_id = await _resolve_owner_chat(message)
    if chat_id is None:
        return

    if not message.reply_to_message:
        await reply_usage(message)
        return

    reply = message.reply_to_message
    if not reply.document or not (reply.document.file_name or "").endswith(".json"):
        await reply_usage(message)
        return

    if (reply.document.file_size or 0) > MAX_IMPORT_FILE_SIZE:
        await message.reply_text(
            tr(
                "import_export.that_file_is_too_large_to_import",
                max_import_file_size=MAX_IMPORT_FILE_SIZE // (1024 * 1024),
            )
        )
        return

    async with asyncio.timeout(60):
        file_obj = await reply.download(in_memory=True)
    if file_obj is None:
        return
    with file_obj:
        if file_obj.getbuffer().nbytes > MAX_IMPORT_FILE_SIZE:
            await message.reply_text(tr("import_export.import_failed_the_file_may_be_malformed"))
            return
        try:
            settings = orjson.loads(file_obj.getvalue())
        except orjson.JSONDecodeError:
            await message.reply_text(tr("import_export.that_file_isn_t_valid_json"))
            return

    if not isinstance(settings, dict):
        await message.reply_text(tr("import_export.malformed_settings_file_expected_a_json_object"))
        return

    try:
        _validate_settings(settings)
    except ValueError:
        await message.reply_text(tr("import_export.import_failed_the_file_may_be_malformed"))
        return

    applied = []
    try:
        for key, value in settings.items():
            collection = collections.get(key)
            if collection is None:
                continue
            value = _portable_settings(key, value)
            if not value:
                continue
            if key == "welcome" and "captcha" in value:
                captcha = value.pop("captcha")
                value.update({f"captcha.{field}": item for field, item in captcha.items()})
            value["chat_id"] = chat_id
            await atomic_upsert(collection, {"chat_id": chat_id}, {"$set": value})
            applied.append(key)
            await invalidate_settings(chat_id, key)
    except Exception:
        LOGGER.exception("Settings import failed for chat %s", chat_id)
        await message.reply_text(
            tr("import_export.import_partially_applied", applied=", ".join(applied))
            if applied
            else tr("import_export.import_unavailable")
        )
        return

    if not applied:
        await message.reply_text(tr("import_export.nothing_recognizable_to_import_in_that_file"))
        return

    await message.reply_text(tr("import_export.settings_imported", applied=", ".join(applied)))


@command(
    "chatreset", rate_limit=Config.RATE_LIMIT_SUPER_HEAVY, chat_scope="group", allow_connected=True
)
@anonadmin_checker(owner_only=True)
async def reset_settings(client, message):
    chat_id = await _resolve_owner_chat(message)
    if chat_id is None:
        return

    await send_confirmation(
        message,
        tr("import_export.this_will_permanently_delete_blocklists_filters_locks"),
        "chat_reset",
        {"chat_id": chat_id},
        [
            ("chatresetyes", tr("import_export.confirm_reset"), ButtonStyle.DANGER),
            ("chatresetno", tr("buttons.cancel"), ButtonStyle.DEFAULT),
        ],
        client=client,
    )


@callbackquery(pattern=r"^chatresetyes_", access=CallbackAccess(public=True))
async def _chatreset_confirm(client, query):
    data = await authorize_chat_confirmation(client, query, "chat_reset", owner=True)
    if data is None:
        return
    chat_id = data["chat_id"]

    for collection in collections.values():
        await collection.delete_one({"chat_id": chat_id})
    for key in collections:
        await invalidate_settings(chat_id, key)

    await query.answer(tr("import_export.settings_reset"))
    await query.message.edit_text(tr("import_export.all_chat_settings_have_been_reset"))


@callbackquery(pattern=r"^chatresetno_", access=CallbackAccess(public=True))
async def _chatreset_cancel(client, query):
    if await authorize_chat_confirmation(client, query, "chat_reset", owner=True) is None:
        return
    await query.answer(tr("clone.cancelled"))
    await query.message.edit_text(tr("import_export.reset_cancelled_no_changes_made"))


async def invalidate_settings(chat_id, key):
    if key == "locks":
        await invalidate_locks(chat_id)
    elif key == "blocklists":
        await blocklist_cache.delete(f"bl:{chat_id}")
