"""End-to-end eval: full graph -> LLM-as-judge scores report quality 1-5.

For each golden question we:

1. Run the planner → researcher → writer → guard graph end-to-end.
2. Ask the chat model to score the report against the question on a 1-5 scale.
3. Mark scores below 3 as failures.

Run:
    uv run python -m evals.e2e_eval
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langsmith import Client, evaluate
from langsmith.evaluation import EvaluationResult, run_evaluator
from langsmith.schemas import Example, Run

from app.llm import get_chat_model
from app.tracing import flush_langsmith_traces, setup_langsmith_tracing
from evals._graph_runner import run_full_graph
from evals.planner_eval import (
    ensure_golden_dataset,
    load_golden,
)

EXPERIMENT_PREFIX = "e2e-eval"
FAIL_BELOW = 3
GOLDEN_PATH = Path(__file__).resolve().parent / "golden.jsonl"

JUDGE_SYSTEM = (
    "You are a strict but fair research-report grader. "
    "Score reports 1 (useless) to 5 (excellent: accurate, well-cited, on-topic). "
    "Return ONLY a JSON object with keys 'score' (integer 1-5) and 'feedback' (string)."
)
JUDGE_USER = (
    "Question:\n{question}\n\n"
    "Report:\n{report}\n\n"
    "Expected coverage keywords: {expected_sections}\n"
    "Minimum citations: {min_citations}\n\n"
    "Return ONLY JSON: {{\"score\": <1-5>, \"feedback\": \"...\"}}"
)


def run_graph_for_eval(inputs: dict) -> dict:
    """LangSmith target: run the full graph and surface the report."""
    question = inputs["question"]
    final_state = run_full_graph(question)
    return {
        "report": (final_state or {}).get("report") or "",
        "findings_count": len(final_state.get("findings") or []),
    }


def _message_text(content: str | list) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return "\n".join(part for part in parts if part)


def _parse_judge_response(text: str) -> tuple[int, str]:
    """Pull an integer 1-5 ``score`` and ``feedback`` out of the judge reply."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

    try:
        payload = json.loads(text)
        score = int(payload.get("score", 0))
        feedback = str(payload.get("feedback", ""))
        return max(1, min(5, score)), feedback
    except (json.JSONDecodeError, TypeError, ValueError):
        match = re.search(r"\b([1-5])\b", text)
        score = int(match.group(1)) if match else 1
        return score, text[:200]


@run_evaluator
def quality_judge(run: Run, example: Example) -> EvaluationResult:
    """LLM-as-judge: 1-5 quality score on the generated report."""
    outputs = run.outputs or {}
    inputs = example.inputs or {}
    expected = example.outputs or {}
    report = outputs.get("report") or ""
    question = inputs.get("question") or ""

    if not report.strip():
        return EvaluationResult(
            key="quality",
            score=0.0,
            comment="FAIL: empty report",
        )

    model = get_chat_model()
    reply = model.invoke(
        [
            SystemMessage(content=JUDGE_SYSTEM),
            HumanMessage(
                content=JUDGE_USER.format(
                    question=question,
                    report=report,
                    expected_sections=expected.get("expected_sections") or [],
                    min_citations=expected.get("min_citations") or 0,
                )
            ),
        ]
    )
    score_int, feedback = _parse_judge_response(_message_text(reply.content))

    normalised = (score_int - 1) / 4.0  # map 1..5 to 0.0..1.0 for LangSmith
    passed = score_int >= FAIL_BELOW
    comment = f"{'PASS' if passed else 'FAIL'} score={score_int}/5 — {feedback[:160]}"
    return EvaluationResult(key="quality", score=normalised, comment=comment)


def _print_summary(results) -> int:
    rows = list(results)
    if not rows:
        print("No evaluation rows returned.")
        return 1

    passed = 0
    print(f"\n{'=' * 78}")
    print(f"E2E eval — fail below score {FAIL_BELOW}/5")
    print(f"{'=' * 78}")

    threshold_normalised = (FAIL_BELOW - 1) / 4.0
    for index, row in enumerate(rows, start=1):
        question = row["example"].inputs.get("question", "")
        eval_results = row["evaluation_results"].get("results") or []
        score = eval_results[0].score if eval_results else 0.0
        comment = eval_results[0].comment if eval_results else ""
        ok = (score or 0.0) >= threshold_normalised
        passed += int(ok)
        status = "PASS" if ok else "FAIL"
        snippet = question if len(question) <= 56 else question[:53] + "..."
        # Reconstruct the integer 1-5 score for display.
        score_int = max(1, min(5, round((score or 0.0) * 4 + 1)))
        print(f"{index:2d}. [{status}] score={score_int}/5  {snippet}")
        if comment:
            print(f"      → {comment}")

    total = len(rows)
    pct = 100.0 * passed / total
    print(f"{'-' * 78}")
    print(f"Aggregate: {passed}/{total} passed ({pct:.0f}%)")
    print(f"Experiment: {results.experiment_name}")
    return 0 if passed == total else 1


def main() -> int:
    setup_langsmith_tracing()
    rows = load_golden()
    if not rows:
        print(f"No rows found in {GOLDEN_PATH}", file=sys.stderr)
        return 1

    print(f"Loaded {len(rows)} golden questions from {GOLDEN_PATH.name}")
    client = Client()
    dataset_name = ensure_golden_dataset(client, rows)

    results = evaluate(
        run_graph_for_eval,
        data=dataset_name,
        evaluators=[quality_judge],
        experiment_prefix=EXPERIMENT_PREFIX,
        description="End-to-end quality eval: full graph + 1-5 LLM-as-judge.",
        max_concurrency=2,
        client=client,
    )
    exit_code = _print_summary(results)
    flush_langsmith_traces()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
