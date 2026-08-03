"""Parse relative time windows like 30m, 1h, 2d."""

from __future__ import annotations

import re
from datetime import timedelta


def parse_since(since: str) -> timedelta:
    text = (since or "1h").strip().lower()
    match = re.fullmatch(r"(\d+)([smhd])", text)
    if not match:
        return timedelta(hours=1)
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)
