# Monk project Starter Repo

This is the starter repo for the **Monk Technologies Agentic AI project**. By the end of the project, this folder will contain two production-grade AI agents (Research Assistant + Ticket Triage Agent) running on AWS Bedrock (OpenAI's open-weight `gpt-oss-120b`) and Google Cloud Vertex AI (Gemini), deployed to Cloud Run and AgentCore / Agent Engine.

## What's already in here

- `pyproject.toml` - pinned Python dependencies.
- `docker-compose.yml` - a local pgvector database.
- `.env` - your local secrets (gitignored; create and fill in before Day 1).
- `scripts/setup_aws.sh`, `scripts/setup_gcp.sh` - guided cloud setup (run once).
- `scripts/deploy_cloudrun.sh`, `scripts/deploy_agentcore.sh`, `scripts/deploy_vertex_engine.sh` - one-command deploys.
- `app/smoke.py` - the Day-0 smoke test you ran in pre-work.
- `app/llm.py` - the model-provider abstraction we'll use everywhere.
- `data/` - sample doc corpora and ticket datasets for the projects.
- `.cursor/rules/` - house style + project-specific rules. Cursor reads these automatically.

## What you'll add during the project

- `app/hello_agent.py` (Day 1)
- `app/tools/` (Day 2)
- `app/nodes/`, `app/graph.py` (Day 3)
- `app/main.py`, `app/ui/` (Day 3-4)
- `app/agents/`, `app/memory/`, `app/hitl.py` (Day 5-6)
- `deploy/agentcore_entrypoint.py`, `deploy/vertex_engine_deploy.py` (Day 7)
- `evals/`, `security/` (Day 4 and Day 8)

## Quick start

```bash
# 1. Install deps
uv sync

# 2. Start the local vector DB
docker compose up -d postgres

# 3. Verify cloud access (one-time)
./scripts/setup_aws.sh
./scripts/setup_gcp.sh

# 4. Smoke test
uv run python -m app.smoke
```

If step 4 prints "All systems go" you are ready for Day 1.

## Common make targets

```bash
make help            # list targets
make smoke           # run the smoke test
make tools           # tool smoke test (LangSmith tracing on by default)
make tracing-check   # verify LangSmith API key + endpoint
make ingest CORPUS=aws-docs   # ingest a sample corpus into pgvector
make dev             # run the FastAPI app with reload
make eval            # run all evals
make deploy-cloudrun # deploy Project 1 to Cloud Run
make deploy-agentcore # deploy Project 2 to Bedrock AgentCore
make deploy-vertex   # deploy Project 2 to Vertex AI Agent Engine
```

LangSmith event tracking is **on by default** when `LANGSMITH_API_KEY` is in `.env`.
Opt out for one run with `make tools-notrace` or `MONK_NO_TRACE=1 uv run python -m app.tools`.

## Folder map (final state, end of Day 8)

```
.
├── app/
│   ├── smoke.py            (Day 0 - already here)
│   ├── llm.py              (Day 0 - already here)
│   ├── hello_agent.py      (Day 1)
│   ├── tools/              (Day 2)
│   ├── nodes/              (Day 3, Project 1)
│   ├── graph.py            (Day 3-6)
│   ├── main.py             (Day 3-6)
│   ├── ui/                 (Day 3-6)
│   ├── agents/             (Day 5-6, Project 2)
│   ├── memory/             (Day 5-6, Project 2)
│   ├── hitl.py             (Day 6, Project 2)
│   └── guardrails.py       (Day 4 + Day 8)
├── data/                   (already populated with samples)
├── evals/                  (Day 4 + Day 8)
├── security/               (Day 8)
├── deploy/                 (Day 7)
├── scripts/                (already here)
├── .cursor/rules/          (already here)
├── docker-compose.yml
├── Dockerfile
├── Makefile
├── pyproject.toml
└── .env
```
