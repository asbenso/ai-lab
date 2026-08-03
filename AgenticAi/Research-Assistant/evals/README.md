# Evals

Eval scripts live here. On Day 4 (Project 1) and Day 8 (Project 2) we add:

- `golden.jsonl` - the golden dataset(s).
- `planner_eval.py`, `citation_eval.py`, `e2e_eval.py` (Project 1).
- `triager_eval.py`, `investigator_eval.py`, `responder_eval.py`, `e2e_eval.py` (Project 2).
- `run_all.py` - convenience script that runs whichever ones exist.

We use **LangSmith** as the eval backbone. Each script:

1. Loads a golden dataset.
2. Runs the agent / node against each row.
3. Scores with a mix of programmatic checks and LLM-as-judge.
4. Uploads to LangSmith as an experiment for side-by-side comparison.

See the Cursor prompts in `cursor-prompts/project*-prompts.md` for the exact prompts that generate each eval script.
