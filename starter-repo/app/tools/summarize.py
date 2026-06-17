"""LLM-powered text summarization."""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.tools import tool
from langsmith import traceable

DEFAULT_MODEL = "bedrock_converse:openai.gpt-oss-120b-1:0"


def _message_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "".join(parts) if parts else str(content)


def _summary_prompt(text: str, focus: str) -> str:
    if focus:
        return (
            f"Summarize the following text in exactly 3 sentences. "
            f"Emphasise {focus!r} throughout the summary.\n\n{text}"
        )
    return f"Summarize the following text in exactly 3 sentences.\n\n{text}"


@traceable(run_type="tool", name="summarize")
def _run_summarize(text: str, focus: str = "") -> str:
    model_name = os.getenv("MONK_MODEL", DEFAULT_MODEL)
    model = init_chat_model(model_name)
    response = model.invoke(_summary_prompt(text, focus))
    return _message_text(response.content).strip()


@tool
def summarize(text: str, focus: str = "") -> str:
    """Condense long text into a three-sentence summary, optionally weighted toward a topic. Use this when fetched pages or notes are too long to fit in context and you need the key points first."""
    return _run_summarize(text, focus)


if __name__ == "__main__":
    from app.tools._smoke_demo import demo_summarize

    demo_summarize()
