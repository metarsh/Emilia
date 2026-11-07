import asyncio
import secrets
from datetime import UTC, datetime, timedelta
from weakref import WeakValueDictionary

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pyrogram.errors import RPCError

from Emilia.application import LOGGER, db
from Emilia.database.common import atomic_find_one_and_update, atomic_upsert

_LOCKS = WeakValueDictionary()


async def create_invoice(user_id: int, amount: int) -> str:
    payload = f"cloneslot:{user_id}:{secrets.token_urlsafe(12)}"
    await db.clone_invoices.insert_one(
        {
            "_id": payload,
            "user_id": user_id,
            "currency": "XTR",
            "amount": amount,
            "expires_at": datetime.now(UTC) + timedelta(days=7),
        }
    )
    return payload


async def validate_invoice(
    payload: str, user_id: int, currency: str, amount: int, *, checkout: bool = False
) -> bool:
    invoice = await db.clone_invoices.find_one({"_id": payload})
    if (
        not invoice
        or invoice["user_id"] != user_id
        or invoice["currency"] != currency
        or invoice["amount"] != amount
    ):
        return False
    expiry = invoice["expires_at"]
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    return not checkout or expiry > datetime.now(UTC)


async def _record_payment(
    user_id: int, charge_id: str, amount: int, payload: str, *, refund_pending: bool = False
):
    receipt = {
        "_id": charge_id,
        "user_id": user_id,
        "stars": amount,
        "payload": payload,
        "created_at": datetime.now(UTC),
        "granted": False,
        "refunded": False,
    }
    if refund_pending:
        receipt["refund_pending"] = True
    try:
        await db.clone_payments.insert_one(receipt)
    except DuplicateKeyError:
        receipt = await db.clone_payments.find_one({"_id": charge_id})
        if (
            not receipt
            or receipt["user_id"] != user_id
            or receipt["stars"] != amount
            or receipt["payload"] != payload
        ):
            raise ValueError("Payment receipt does not match")
    return receipt


async def grant_slot(user_id: int, charge_id: str, amount: int, payload: str) -> bool:
    """The charge ID and balance increment are committed in the same document."""
    receipt = await _record_payment(user_id, charge_id, amount, payload)
    if receipt.get("granted") or receipt.get("refunded") or receipt.get("refund_pending"):
        return False
    applied = {"$ifNull": ["$applied_payments", []]}
    refunded = {"$ifNull": ["$applied_refunds", []]}
    eligible = {
        "$and": [
            {"$not": [{"$in": [{"$literal": charge_id}, applied]}]},
            {"$not": [{"$in": [{"$literal": charge_id}, refunded]}]},
        ]
    }
    previous = await atomic_find_one_and_update(
        db.clone_slots,
        {"_id": user_id},
        [
            {
                "$set": {
                    "extra": {"$add": [{"$ifNull": ["$extra", 0]}, {"$cond": [eligible, 1, 0]}]},
                    "applied_payments": {
                        "$cond": [
                            eligible,
                            {"$setUnion": [applied, {"$literal": [charge_id]}]},
                            applied,
                        ]
                    },
                }
            }
        ],
        return_document=ReturnDocument.BEFORE,
    )
    previous = previous or {}
    added = charge_id not in previous.get("applied_payments", []) and charge_id not in previous.get(
        "applied_refunds", []
    )
    await db.clone_payments.update_one({"_id": charge_id}, {"$set": {"granted": True}})
    return added


async def refund_invalid_payment(
    user_id: int, charge_id: str, amount: int, payload: str, client
) -> bool:
    """Record rejected Star invoices before refunding so recovery can retry them."""
    await _record_payment(user_id, charge_id, amount, payload, refund_pending=True)
    return await refund_slot(charge_id, client)


async def refund_slot(charge_id: str, client) -> bool:
    lock = _LOCKS.setdefault(charge_id, asyncio.Lock())
    async with lock:
        receipt = await db.clone_payments.find_one({"_id": charge_id})
        if not receipt:
            raise ValueError("Payment not found")
        if receipt.get("refunded"):
            return False
        await db.clone_payments.update_one({"_id": charge_id}, {"$set": {"refund_pending": True}})
        try:
            accepted = await client.refund_star_payment(
                user_id=receipt["user_id"], telegram_payment_charge_id=charge_id
            )
            if not accepted:
                raise RuntimeError("Telegram rejected the refund")
        except RPCError as exc:
            identifier = getattr(exc, "ID", type(exc).__name__)
            if identifier not in {
                "STARS_ALREADY_REFUNDED",
                "PAYMENT_ALREADY_REFUNDED",
                "StarsAlreadyRefunded",
                "PaymentAlreadyRefunded",
            }:
                raise
        # Upsert by the stable user key; the pipeline itself is idempotent.
        await atomic_upsert(
            db.clone_slots,
            {"_id": receipt["user_id"]},
            [
                {
                    "$set": {
                        "extra": {
                            "$max": [
                                0,
                                {
                                    "$subtract": [
                                        {"$ifNull": ["$extra", 0]},
                                        {
                                            "$cond": [
                                                {
                                                    "$and": [
                                                        {
                                                            "$in": [
                                                                {
                                                                    "$literal": charge_id,
                                                                },
                                                                {
                                                                    "$ifNull": [
                                                                        "$applied_payments",
                                                                        [],
                                                                    ]
                                                                },
                                                            ]
                                                        },
                                                        {
                                                            "$not": [
                                                                {
                                                                    "$in": [
                                                                        {"$literal": charge_id},
                                                                        {
                                                                            "$ifNull": [
                                                                                "$applied_refunds",
                                                                                [],
                                                                            ]
                                                                        },
                                                                    ]
                                                                }
                                                            ]
                                                        },
                                                    ]
                                                },
                                                1,
                                                0,
                                            ]
                                        },
                                    ]
                                },
                            ]
                        },
                        "applied_refunds": {
                            "$setUnion": [
                                {"$ifNull": ["$applied_refunds", []]},
                                {"$literal": [charge_id]},
                            ]
                        },
                    }
                }
            ],
        )
        await db.clone_payments.update_one(
            {"_id": charge_id}, {"$set": {"refunded": True}, "$unset": {"refund_pending": ""}}
        )
        return True


async def recover_payments(client):
    async for receipt in db.clone_payments.find(
        {
            "$or": [
                {"granted": False, "refunded": {"$ne": True}},
                {"refund_pending": True, "refunded": {"$ne": True}},
            ]
        }
    ).batch_size(100):
        try:
            if receipt.get("refund_pending"):
                await refund_slot(receipt["_id"], client)
            else:
                await grant_slot(
                    receipt["user_id"], receipt["_id"], receipt["stars"], receipt["payload"]
                )
        except Exception:
            LOGGER.exception("Could not recover a pending clone payment")


async def payment_recovery_loop(client):
    while True:
        await recover_payments(client)
        await asyncio.sleep(60)
