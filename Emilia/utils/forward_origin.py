def fwd_user(message):
    return getattr(getattr(message, "forward_origin", None), "sender_user", None)


def fwd_chat(message):
    origin = getattr(message, "forward_origin", None)
    return getattr(origin, "chat", getattr(origin, "sender_chat", None))


def fwd_date(message):
    return getattr(getattr(message, "forward_origin", None), "date", None)
