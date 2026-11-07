from Emilia.config import Config

DEV_SET = {int(x) for x in (Config.DEV_USERS or [])}
DEV_SET.add(int(Config.OWNER_ID))


def is_owner(user_id: int) -> bool:
    try:
        return int(user_id) == int(Config.OWNER_ID)
    except (TypeError, ValueError, OverflowError):
        return False


def is_dev(user_id: int) -> bool:
    try:
        return int(user_id) in DEV_SET
    except (TypeError, ValueError, OverflowError):
        return False
