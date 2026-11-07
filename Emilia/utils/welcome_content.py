from Emilia.utils.saved_message import parse_saved_message


def GetWelcomeMessage(message):
    return parse_saved_message(message, named=False)
