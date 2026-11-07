"""manages languages, strings"""

import json
from pathlib import Path
from string import Formatter

from Emilia.config import Config


def _fields(template):
    return {field for _, field, _, _ in Formatter().parse(template) if field is not None}


def load_catalogue(language: str = "en") -> dict[str, str]:
    root = Path(__file__).parent
    defaults = json.loads((root / "en/messages.json").read_text(encoding="utf-8"))
    if language != "en":
        custom = json.loads((root / language / "messages.json").read_text(encoding="utf-8"))
        if not isinstance(custom, dict):
            raise ValueError(f"{language}/messages.json must contain a JSON object")
        for key, value in custom.items():
            if key not in defaults or not isinstance(value, str):
                raise ValueError(f"Unknown or invalid message: {key}")
            if _fields(value) != _fields(defaults[key]):
                raise ValueError(f"Message placeholders differ: {key}")
        defaults.update(custom)
    return defaults


_CATALOGUE = load_catalogue(Config.LANGUAGE)


def tr(key: str, **values) -> str:
    template = _CATALOGUE[key]
    defaults = {
        "bot_name": Config.BOT_NAME,
        "support_contact": f"@{Config.SUPPORT_CHAT}"
        if Config.SUPPORT_CHAT
        else "the deployment operator",
    }
    if values:
        return template.format_map({**defaults, **values})
    for name, value in defaults.items():
        template = template.replace("{" + name + "}", value)
    return template
