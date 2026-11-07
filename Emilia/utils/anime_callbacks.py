from Emilia.utils.cb_token import stash, unstash


async def list_callback(state: dict, *, client, query=None) -> str:
    token = await stash(
        state,
        client=client,
        chat_id=query.message.chat.id if query else None,
        message_id=query.message.id if query else None,
    )
    return ("almenu:" if state["action"] in ("lsadd", "lsupdt") else "alset:") + token


async def read_list_callback(query, *, client):
    if query.data.startswith(("almenu:", "alset:")):
        state = await unstash(
            query.data.partition(":")[2],
            client=client,
            chat_id=query.message.chat.id,
            message_id=query.message.id,
        )
        return state if _valid_state(state) else None
    # Read menus sent before token-based callbacks were introduced.
    fields = query.data.split("_")
    action = fields[0]
    selecting = action in ("lsadd", "lsupdt")
    if not selecting and action not in ("lsas", "lsus", "dlt"):
        return None
    try:
        start = 1 if selecting else 2
        media, media_id = fields[start : start + 2]
        remaining = fields[start + 2 : -1]
        list_id = int(remaining.pop(0)) if action in ("lsupdt", "lsus", "dlt") else None
        state = {
            "action": action,
            "media": media,
            "media_id": int(media_id),
            "list_id": list_id,
            "query": remaining[0] if remaining else None,
            "page": int(remaining[1]) if len(remaining) > 1 else None,
            "owner": int(fields[-1]),
            "status": fields[1] if not selecting else None,
        }
        return state if _valid_state(state) else None
    except (ValueError, IndexError):
        return None


def _valid_state(state):
    if (
        not isinstance(state, dict)
        or not {"action", "media", "media_id", "list_id", "query", "page", "owner"} <= state.keys()
    ):
        return False
    return (
        state["action"] in {"lsadd", "lsupdt", "lsas", "lsus", "dlt"}
        and state["media"] in {"ANIME", "MANGA", "AIRING"}
        and isinstance(state["media_id"], int)
        and state["media_id"] > 0
        and isinstance(state["owner"], int)
        and state["owner"] != 0
        and (state["list_id"] is None or isinstance(state["list_id"], int))
        and (state["query"] is None or isinstance(state["query"], str))
        and (state["page"] is None or isinstance(state["page"], int) and state["page"] > 0)
    )
