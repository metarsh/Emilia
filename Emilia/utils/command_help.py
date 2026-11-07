import json
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path

from Emilia.config import Config
from Emilia.locales import tr

COMMAND_HELP = ContextVar("command_help", default=None)


@lru_cache(maxsize=1)
def _catalogue():
    path = Path(__file__).parents[1] / "locales/en/commands.json"
    return json.loads(path.read_text(encoding="utf-8"))


def attach_command_help(func, name, *, usage=None, description=None, example=None):
    metadata = _catalogue().get(f"{func.__module__}.{func.__qualname__}", {})
    token = name.split("|", 1)[0].strip("()")
    values = {
        "usage": usage or metadata.get("usage") or f"/{token}",
        "description": description
        or metadata.get("description")
        or (func.__doc__ or f"Run /{token}.").strip().split("\n", 1)[0],
        "example": example or metadata.get("example") or f"/{token}",
    }
    for field, value in values.items():
        if isinstance(value, dict):
            value = tr(value["key"])
        setattr(
            func, field, value.replace("{command}", token).replace("{bot_name}", Config.BOT_NAME)
        )
    return func


async def reply_usage(message, func=None):
    func = func or COMMAND_HELP.get()
    if func is None:
        raise ValueError("reply_usage requires a registered command or an explicit handler")
    from Emilia.locales.help import HelpPage
    from Emilia.utils.help_rendering import show_help_page

    content = (
        f"{func.description}\n\n## Usage\n\n`{func.usage}`"
        f"\n\n## Example\n\n```\n{func.example}\n```"
    )
    return await show_help_page(
        message._client, message, HelpPage("help", "Command help", content), None
    )
