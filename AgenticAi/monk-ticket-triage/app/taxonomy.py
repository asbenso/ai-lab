"""Load domain taxonomy files."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


@lru_cache(maxsize=8)
def load_taxonomy(domain: str) -> dict[str, Any]:
    """Load ``data/{domain}/taxonomy.yaml``."""
    path = DATA_DIR / domain / "taxonomy.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"Taxonomy not found for domain {domain!r}: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid taxonomy file: {path}")
    return data


def category_names(taxonomy: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for item in taxonomy.get("categories") or []:
        if isinstance(item, dict) and item.get("name"):
            names.add(str(item["name"]))
    return names


def format_taxonomy_for_prompt(taxonomy: dict[str, Any]) -> str:
    """Render categories and severities for the triager prompt."""
    names: list[str] = []
    detail_lines: list[str] = []
    for item in taxonomy.get("categories") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        description = str(item.get("description", ""))
        if name:
            names.append(name)
            detail_lines.append(f"- {name}: {description}")
    severities = taxonomy.get("severities") or ["P1", "P2", "P3", "P4"]
    severity_text = ", ".join(str(level).split()[0] for level in severities)
    return (
        f"{', '.join(names)}\n"
        + "\n".join(detail_lines)
        + f"\nSeverities: {severity_text}"
    )
