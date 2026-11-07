from Emilia.utils.saved_message import parse_saved_message


def GetNoteMessage(message):
    return parse_saved_message(message, video_note_text="")
