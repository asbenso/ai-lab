"""Planner coverage eval against the golden dataset.

Run:
    uv run python -m evals.planner_eval
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage
from langsmith import Client, evaluate
from langsmith.evaluation import EvaluationResult, run_evaluator
from langsmith.schemas import Example, Run

from app.llm import get_chat_model
from app.nodes.planner import planner_node
from app.tracing import flush_langsmith_traces, setup_langsmith_tracing

GOLDEN_PATH = Path(__file__).resolve().parent / "golden.jsonl"
DATASET_NAME = "project1-golden"
PASS_THRESHOLD = 0.7
EXPERIMENT_PREFIX = "planner-eval"

JUDGE_PROMPT = (
    "Given the sub-questions {sqs} and the expected coverage areas "
    "{expected_sections}, return a number 0.0-1.0 representing how well the "
    "sub-questions cover the expected areas. Return only a number."
)


def load_golden(path: Path = GOLDEN_PATH) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _golden_example_payloads(rows: list[dict]) -> list[dict]:
    return [
        {
            "inputs": {"question": row["question"]},
            "outputs": {
                "expected_sections": row["expected_sections"],
                "min_citations": row["min_citations"],
            },
        }
        for row in rows
    ]


def ensure_golden_dataset(client: Client, rows: list[dict]) -> str:
    """Create/sync the golden dataset in LangSmith (evaluate needs a real dataset)."""
    if not client.has_dataset(dataset_name=DATASET_NAME):
        client.create_dataset(
            DATASET_NAME,
            description="Project 1 golden research questions for evals.",
        )

    existing = list(client.list_examples(dataset_name=DATASET_NAME, limit=1))
    if not existing:
        client.create_examples(
            dataset_name=DATASET_NAME,
            examples=_golden_example_payloads(rows),
        )
        print(f"Uploaded {len(rows)} examples to LangSmith dataset {DATASET_NAME!r}")
    else:
        print(f"Using existing LangSmith dataset {DATASET_NAME!r}")

    return DATASET_NAME


def run_planner(inputs: dict) -> dict:
    """LangSmith target: run ``planner_node`` on a single golden question."""
    question = inputs["question"]
    result = planner_node(
        {
            "question": question,
            "sub_questions": [],
            "findings": [],
            "report": "",
            "memories": [],
            "step_log": [],
        }
    )
    return {"sub_questions": result.get("sub_questions") or []}


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


def _parse_judge_score(text: str) -> float:
    match = re.search(r"\b(1(?:\.0+)?|0(?:\.\d+)?)\b", text.strip())
    if not match:
        return 0.0
    score = float(match.group(1))
    return max(0.0, min(1.0, score))


def _llm_coverage_score(sub_questions: list[dict], expected_sections: list[str]) -> float:
    model = get_chat_model()
    reply = model.invoke(
        [
            HumanMessage(
                content=JUDGE_PROMPT.format(
                    sqs=sub_questions,
                    expected_sections=expected_sections,
                )
            )
        ]
    )
    return _parse_judge_score(_message_text(reply.content))


@run_evaluator
def coverage_judge(run: Run, example: Example) -> EvaluationResult:
    """LLM-as-judge: how well sub-questions cover expected section keywords."""
    sub_questions = (run.outputs or {}).get("sub_questions") or []
    expected_sections = (example.outputs or {}).get("expected_sections") or []
    score = _llm_coverage_score(sub_questions, expected_sections)
    passed = score >= PASS_THRESHOLD
    return EvaluationResult(
        key="coverage",
        score=score,
        comment=f"{'PASS' if passed else 'FAIL'} (threshold {PASS_THRESHOLD})",
    )


def _print_summary(results) -> int:
    rows = list(results)
    if not rows:
        print("No evaluation rows returned.")
        return 1

    passed = 0
    print(f"\n{'=' * 72}")
    print(f"Planner eval — threshold {PASS_THRESHOLD}")
    print(f"{'=' * 72}")
    for index, row in enumerate(rows, start=1):
        question = row["example"].inputs.get("question", "")
        eval_results = row["evaluation_results"].get("results") or []
        score = eval_results[0].score if eval_results else 0.0
        ok = (score or 0.0) >= PASS_THRESHOLD
        passed += int(ok)
        status = "PASS" if ok else "FAIL"
        snippet = question if len(question) <= 60 else question[:57] + "..."
        print(f"{index:2d}. [{status}] score={score:.2f}  {snippet}")

    total = len(rows)
    pct = 100.0 * passed / total
    print(f"{'-' * 72}")
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
        run_planner,
        data=dataset_name,
        evaluators=[coverage_judge],
        experiment_prefix=EXPERIMENT_PREFIX,
        description="Planner coverage vs expected_sections (LLM-as-judge).",
        max_concurrency=2,
        client=client,
    )
    exit_code = _print_summary(results)
    flush_langsmith_traces()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
