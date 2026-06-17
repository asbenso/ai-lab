# Monk Technologies - Cursor Prompt Library

This folder is the instructor's (and the learners') copy-paste-ready library of Cursor prompts for the Agentic AI Bootcamp.

## Runnable code

The Python starter repo lives in **`starter-repo/`** (nested one level). From the git root:

```bash
make tools             # web_search -> fetch_url -> summarize
make tracing-check     # verify LangSmith
```

Or `cd starter-repo && uv sync && make tools`. Configure API keys in `starter-repo/.env` (gitignored).

## How to use

1. Open the bootcamp's starter repo in Cursor.
2. Confirm the right `.cursor/rules/` files are in place (we ship them inside the starter repo, not here). They live next to this folder for reference, in [.cursor/rules/](.cursor/rules/).
3. When the project plan tells you to issue a prompt, find it in the corresponding file below and paste it into Cursor Composer (Cmd-I on Mac).

## Files

- [project1-prompts.md](project1-prompts.md) - every prompt for Project 1 (AI Research Assistant), in chronological order.
- [project2-prompts.md](project2-prompts.md) - every prompt for Project 2 (Autonomous Ticket Triage Agent), in chronological order.
- [warmup-prompts.md](warmup-prompts.md) - Day 1 + Day 2 prompts (foundations, not yet project-specific).
- [.cursor/rules/](.cursor/rules/) - the project-level rule files that ship with the starter repo.

## Cursor usage conventions we follow in this bootcamp

- **Composer over inline edits** when creating new files or making cross-file changes.
- **Inline edits** (Cmd-K) when refactoring within a single file.
- **Tab completion** for one-line boilerplate (type hints, imports).
- **Agent mode** is reserved for the instructor; learners use Composer.
- **Always read what Cursor writes** before saving. The bootcamp grades on understanding, not on volume of code.

## How prompts in this library are formatted

Each prompt block is bounded by a fenced quote and is meant to be pasted verbatim. The wording is deliberately concrete (file paths, type hints, function signatures, return types) so that Cursor produces consistent output even with different models behind it.

If you (the instructor) want to demo improvising a prompt, do that in addition to a copy-paste, not instead of.

## A note on model selection

The prompts assume Cursor is configured with **Claude Sonnet 4 / Opus 4** (or Sonnet 4.5+) for Composer. If learners are on a free tier and falling back to a smaller model, expect more nudging on imports and type hints. Add a follow-up: "Add missing imports and run `ruff check`."
