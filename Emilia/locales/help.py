"""Help pages discovered from locales/<language>/help/*.md."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from Emilia.config import Config


@dataclass(frozen=True)
class HelpPage:
    id: str
    title: str
    content: str
    children: tuple[str, ...] = ()
    hidden: bool = False
    anime: bool = False

    @property
    def body(self) -> str:
        return self.content.replace("{bot_name}", Config.BOT_NAME)


def load_help(language: str = "en") -> dict[str, HelpPage]:
    directory = Path(__file__).parent / language / "help"
    if not directory.is_dir():
        directory = Path(__file__).parent / "en/help"
    pages = {}
    for path in sorted(directory.glob("*.md")):
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,24}", path.stem):
            raise ValueError(f"Help filename must be a short lowercase slug: {path.name}")
        parts = path.read_text(encoding="utf-8").split("+++", 2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError(f"Help page needs TOML metadata between +++ lines: {path.name}")
        metadata = tomllib.loads(parts[1])
        if set(metadata) - {"title", "children", "hidden", "anime"}:
            raise ValueError(f"Unknown help metadata field: {path.name}")
        if any(not isinstance(metadata.get(flag, False), bool) for flag in ("hidden", "anime")):
            raise ValueError(f"Help flags must be true or false: {path.name}")
        title = metadata.get("title")
        children = metadata.get("children", [])
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Help page needs a title: {path.name}")
        if not isinstance(children, list) or any(not isinstance(child, str) for child in children):
            raise ValueError(f"Help children must be a list of page slugs: {path.name}")
        content = parts[2].strip().removeprefix(f"# {title}").lstrip()
        pages[path.stem] = HelpPage(
            path.stem,
            title,
            content,
            tuple(children),
            metadata.get("hidden", False),
            metadata.get("anime", False),
        )
    for page in pages.values():
        for child in page.children:
            if child not in pages:
                raise ValueError(f"Unknown help page {child!r} linked from {page.id}.md")
    return pages


HELP_PAGES = load_help(Config.LANGUAGE)
ANIME_HELP = {key: page for key, page in HELP_PAGES.items() if page.anime}
