# whether to turn on reporting to admins in a group chat or not

from Emilia.application import db
from Emilia.database.common import atomic_upsert

reports = db.reports


async def reports_db(chat_id: int, report_arg: bool):
    await atomic_upsert(reports, {"chat_id": chat_id}, {"$set": {"reports": report_arg}})


async def get_report(chat_id: int) -> bool:
    doc = await reports.find_one({"chat_id": chat_id}, {"_id": 0, "reports": 1})
    return doc.get("reports", True) if doc else True
