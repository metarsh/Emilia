# save notes in private chat or group chats and get them using # or /note notename

from Emilia.application import db
from Emilia.database.common import atomic_upsert, save_named_entry
from Emilia.utils.message_content import text_value

notes = db.notes


async def SaveNote(chat_id, note_name, content, text, data_type):
    entry = {"note_name": note_name, "content": content, "text": text, "data_type": data_type}
    await save_named_entry(notes, {"chat_id": chat_id}, "notes", "note_name", note_name, entry)


async def GetNote(chat_id, note_name):
    doc = await notes.find_one(
        {"chat_id": chat_id, "notes.note_name": note_name},
        {"_id": 0, "notes": {"$elemMatch": {"note_name": note_name}}},
    )
    if doc and doc.get("notes"):
        n = doc["notes"][0]
        return (n["content"], n["text"], n["data_type"])
    return None


async def isNoteExist(chat_id, note_name) -> bool:
    return (
        await notes.find_one({"chat_id": chat_id, "notes.note_name": note_name}, {"_id": 1})
        is not None
    )


async def NoteList(chat_id) -> list:
    names = []
    doc = await notes.find_one(
        {"chat_id": chat_id}, {"_id": 0, "notes.text": 1, "notes.note_name": 1}
    )
    if doc and doc.get("notes"):
        for note in doc["notes"]:
            NoteText = note.get("text") or ""
            NoteName = note.get("note_name")
            if not NoteName:
                continue
            if "{admin}" in text_value(NoteText):
                NoteName = f"{NoteName} __{{admin}}__"
            names.append(NoteName)
    return names


async def ClearNote(chat_id, note_name):
    await notes.update_one({"chat_id": chat_id}, {"$pull": {"notes": {"note_name": note_name}}})


async def set_private_note(chat_id, private_note):
    await atomic_upsert(notes, {"chat_id": chat_id}, {"$set": {"private_note": private_note}})


async def is_pnote_on(chat_id) -> bool:
    GetNoteData = await notes.find_one({"chat_id": chat_id}, {"_id": 0, "private_note": 1})
    if GetNoteData is not None:
        return bool(GetNoteData.get("private_note"))
    else:
        return False


async def ClearAllNotes(chat_id):
    await notes.update_one({"chat_id": chat_id}, {"$unset": {"notes": ""}})
