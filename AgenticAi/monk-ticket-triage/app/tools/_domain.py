"""Runtime domain context for tools (set by the Investigator from ticket state)."""

from __future__ import annotations

import os
from contextvars import ContextVar

_domain_ctx: ContextVar[str] = ContextVar("monk_domain", default="support")


def set_domain(domain: str) -> None:
    _domain_ctx.set(domain)


def get_domain() -> str:
    return _domain_ctx.get() or os.getenv("MONK_DOMAIN", "support")
