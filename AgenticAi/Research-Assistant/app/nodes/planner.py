"""Planner node: decompose the user question into sub-questions."""

from __future__ import annotations

import json
import logging
import re
from typing import Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from app.graph import ResearchState
from app.llm import get_chat_model
from app.nodes._retry import call_with_retry
from app.nodes.recall import format_memories_for_planner

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a research planner. Decompose the user's question into 3-7 sub-questions "
    "that, taken together, fully cover the question. Tag each as 'web' "
    "(current/news/general), 'local' (likely in our internal docs corpus), or 'both'. "
    "Output strict JSON."
)


class SubQuestion(BaseModel):
    text: str
    source: Literal["web", "local", "both"]


class PlannerOutput(BaseModel):
    sub_questions: list[SubQuestion]


def _message_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif block.get("type") == "reasoning_content":
                reasoning = block.get("reasoning_content") or {}
                if isinstance(reasoning, dict):
                    parts.append(str(reasoning.get("text", "")))
    return "\n".join(part for part in parts if part)


def _parse_planner_output(raw: AIMessage | None) -> PlannerOutput | None:
    """Recover planner JSON when Bedrock reasoning output bypasses the parser."""
    if raw is None:
        return None
    text = _message_text(raw.content).strip()
    if not text:
        return None
    candidates = [text]
    if not text.startswith("{"):
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            candidates.append(match.group(0))
    for candidate in candidates:
        try:
            return PlannerOutput.model_validate_json(candidate)
        except ValidationError:
            try:
                data = json.loads(candidate)
                return PlannerOutput.model_validate(data)
            except (json.JSONDecodeError, ValidationError):
                continue
    return None


def _invoke_planner(question: str, *, memories: list[dict] | None = None) -> PlannerOutput | None:
    """Ask the model for a plan. Returns None when nothing parseable comes back."""
    memory_block = format_memories_for_planner(memories or [])
    human_content = question
    if memory_block:
        human_content = f"{memory_block}\n\nQuestion:\n{question}"

    model = get_chat_model().with_structured_output(
        PlannerOutput,
        method="function_calling",
        include_raw=True,
    )
    response = call_with_retry(
        model.invoke,
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ],
        label="planner",
    )
    if isinstance(response, PlannerOutput):
        return response
    parsed = response.get("parsed") if isinstance(response, dict) else None
    if isinstance(parsed, PlannerOutput):
        return parsed
    return _parse_planner_output(response.get("raw") if isinstance(response, dict) else None)


def _fallback_plan(question: str) -> PlannerOutput:
    """Single-sub-question plan used when the model can't produce structured output."""
    text = (question or "").strip() or "Research the user's request."
    return PlannerOutput(sub_questions=[SubQuestion(text=text, source="both")])


def planner_node(state: ResearchState) -> dict:
    question = state["question"]
    memories = state.get("memories") or []
    log: list[str] = []
    result: PlannerOutput | None = None

    try:
        result = _invoke_planner(question, memories=memories)
    except Exception as exc:
        logger.warning("planner model call failed after retries: %s", exc)
        log.append(
            f"Planner: model call failed after retries ({type(exc).__name__}: {exc})"
        )

    if result is None:
        log.append("Planner: could not parse structured output, falling back to 1 sub-question")
        result = _fallback_plan(question)

    log.append(f"Planner: {len(result.sub_questions)} sub-questions")
    for index, sq in enumerate(result.sub_questions, start=1):
        log.append(f"Planner: {index}. [{sq.source}] {sq.text}")
    return {
        "sub_questions": [sq.model_dump() for sq in result.sub_questions],
        "step_log": state["step_log"] + log,
    }
