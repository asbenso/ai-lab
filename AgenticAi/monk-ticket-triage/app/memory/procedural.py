"""Procedural memory: versioned responder style prompts on disk."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.tools._paths import DATA_DIR

PROMPTS_DIR = DATA_DIR / "prompts"
Domain = Literal["support", "it-helpdesk", "oncall"]

_DEFAULT_PROMPTS: dict[str, str] = {
    "support": (
        "You are a customer support agent for Monk Technologies. Write empathetic, concise "
        "replies that reference investigation findings. Prefer short paragraphs. Offer clear "
        "next steps. Do not promise refunds, credits, or deadlines unless explicitly approved."
    ),
    "it-helpdesk": (
        "You are an IT helpdesk agent. Write practical troubleshooting replies for employees. "
        "Reference logs, runbooks, and prior tickets when available. Use numbered steps for "
        "remediation. Escalate to network or identity on-call when symptoms match widespread outages."
    ),
    "oncall": (
        "You are an on-call incident responder. Be direct and action-oriented. Summarize blast "
        "radius, likely cause, and immediate mitigation. Reference metrics and recent deploys. "
        "Recommend rollback or escalation when error budgets are burning."
    ),
}


def _prompt_path(domain: str) -> Path:
    return PROMPTS_DIR / f"responder_{domain}.json"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_document(domain: str) -> dict[str, Any]:
    return {
        "domain": domain,
        "versions": [
            {
                "version": 1,
                "created_at": "2026-06-01T00:00:00Z",
                "prompt": _DEFAULT_PROMPTS.get(
                    domain,
                    "You are a support agent. Write a clear, professional reply.",
                ),
            }
        ],
    }


def _load_document(domain: str) -> dict[str, Any]:
    path = _prompt_path(domain)
    if path.is_file():
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict) and isinstance(data.get("versions"), list):
            return data
    return _default_document(domain)


def _save_document(domain: str, document: dict[str, Any]) -> None:
    PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _prompt_path(domain)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def get_responder_prompt(domain: str, version: str | int = "latest") -> str:
    """Return a responder style prompt for the domain."""
    document = _load_document(domain)
    versions = document.get("versions") or []
    if not versions:
        return _DEFAULT_PROMPTS.get(domain, "You are a support agent.")

    if version == "latest":
        entry = versions[-1]
        return str(entry.get("prompt", "")).strip()

    target = int(version)
    for entry in versions:
        if int(entry.get("version", 0)) == target:
            return str(entry.get("prompt", "")).strip()
    raise KeyError(f"Responder prompt version {version!r} not found for domain {domain!r}")


def set_responder_prompt(domain: str, prompt: str) -> int:
    """Append a new prompt version and return its version number."""
    text = prompt.strip()
    if not text:
        raise ValueError("set_responder_prompt() requires non-empty prompt text")

    document = _load_document(domain)
    versions = list(document.get("versions") or [])
    next_version = max((int(v.get("version", 0)) for v in versions), default=0) + 1
    versions.append(
        {
            "version": next_version,
            "created_at": _utc_now(),
            "prompt": text,
        }
    )
    document["domain"] = domain
    document["versions"] = versions
    _save_document(domain, document)
    return next_version


__all__ = ["get_responder_prompt", "set_responder_prompt"]
