from pathlib import Path

MODULE_ROOT = Path(__file__).resolve().parents[1] / "modules"


def plugin_config(*, clone: bool = False) -> dict:
    modules = sorted(
        ".".join(path.relative_to(MODULE_ROOT).with_suffix("").parts)
        for path in MODULE_ROOT.rglob("*.py")
        if path.name != "__init__.py" and "__pycache__" not in path.parts
    )
    return {
        "root": "Emilia.modules",
        "include": [name for name in modules if not (clone and name.startswith("music"))],
    }
