# Agentic AI project — AiProjects

This folder contains both projects, prompt libraries, and shared tooling.

## Projects

| Project | Folder | Description |
|---------|--------|-------------|
| **Project 1** | `Research-Assistant/` | AI Research Assistant |
| **Project 2** | `monk-ticket-triage/` | Autonomous Ticket Triage Agent |

## Quick start

Run commands from **`AgenticAi/`**:

```bash
cd AiProjects/AgenticAi
make tools
make smoke
./monk web-search
```

Or cd into a project:

```bash
cd Research-Assistant
uv sync
make dev          # http://localhost:8000

cd ../monk-ticket-triage
make dev          # http://localhost:8001
```

One-time setup:

```bash
cd Research-Assistant
# edit .env with your API keys (gitignored)
uv sync
docker compose up -d postgres
make ingest CORPUS=aws-docs
```

## Prompt libraries

- [warmup-prompts.md](warmup-prompts.md) — Day 1 + Day 2 foundations
- [project1-prompts.md](project1-prompts.md) — Project 1 (Research Assistant)
- [project2-prompts.md](project2-prompts.md) — Project 2 (Ticket Triage)

## Tech stack

| Layer | Technology |
|---|---|
| Agent framework | LangGraph |
| Models | AWS Bedrock (gpt-oss-120b) · GCP Vertex AI (Gemini) |
| Memory | pgvector (PostgreSQL) |
| Tracing | LangSmith |
| Deploy | Cloud Run · Bedrock AgentCore · Vertex Agent Engine |

## Make targets

```bash
make help              # list targets
make tools             # Project 1 tool smoke tests
make p2-graph          # Project 2 sample ticket demo
make tracing-check     # verify LangSmith API key
```
