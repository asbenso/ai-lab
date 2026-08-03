"""Recall node: load user memories before planning."""

from __future__ import annotations

from typing import Any

from app.graph import ResearchState
from app.memory import get_store, recall


def _user_namespace(config: dict[str, Any] | None) -> tuple[str, str]:
    """Memory namespace keyed by user, not per-request thread_id."""
    configurable = (config or {}).get("configurable") or {}
    user_id = configurable.get("user_id") or "default"
    return ("users", str(user_id))


def recall_node(state: ResearchState, config: dict[str, Any]) -> dict:
    """Pull top-3 memories for the current user and stash them for the planner."""
    store = get_store()
    namespace = _user_namespace(config)
    question = state.get("question") or ""
    memories = recall(store, namespace, question, k=3)
    scored = sum(1 for item in memories if item.get("score") is not None)
    mode = "semantic" if scored else "recent"
    log = state["step_log"] + [
        f"Recall ({mode}): {len(memories)} memories for user {namespace[1]!r}"
    ]
    return {"memories": memories, "step_log": log}


def _memory_lines(memories: list[dict]) -> list[str]:
    lines: list[str] = []
    for item in memories:
        value = item.get("value") or {}
        kind = value.get("kind", "note")
        content = value.get("content") or str(value)
        lines.append(f"- ({kind}) {content}")
    return lines


def format_memories(memories: list[dict], *, header: str) -> str:
    """Render recalled items under a section header."""
    if not memories:
        return ""
    return "\n".join([header, *_memory_lines(memories)])


def format_memories_for_planner(memories: list[dict]) -> str:
    """Render recalled items as a planner preamble."""
    return format_memories(memories, header="Memories:")


def format_memories_for_writer(memories: list[dict]) -> str:
    """Render recalled items for the writer prompt."""
    return format_memories(memories, header="What we know about this user:")


_FORMAT_PREFERENCE_KEYWORDS = (
    "format",
    "bullet",
    "numbered",
    "table",
    "concise",
    "detailed",
    "summary",
    "section",
    "paragraph",
    "tone",
    "style",
    "markdown",
    "heading",
    "list",
    "prose",
    "length",
    "brief",
    "verbose",
    "structure",
    "layout",
    "outline",
)


def _is_format_preference(content: str) -> bool:
    lower = content.lower()
    return any(keyword in lower for keyword in _FORMAT_PREFERENCE_KEYWORDS)


def format_preference_instructions(memories: list[dict]) -> str:
    """Build writer system guidance from recalled format/style preferences."""
    prefs: list[str] = []
    for item in memories:
        value = item.get("value") or {}
        if value.get("kind") != "preference":
            continue
        content = (value.get("content") or "").strip()
        if content and _is_format_preference(content):
            prefs.append(content)
    if not prefs:
        return ""
    bullets = "\n".join(f"- {pref}" for pref in prefs)
    return (
        "Honor these user format/style preferences when structuring the report. "
        "They override the default layout when they conflict:\n"
        f"{bullets}"
    )
