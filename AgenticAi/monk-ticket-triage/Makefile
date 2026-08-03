.PHONY: help install postgres-up ingest-runbooks seed-past-cases graph triager tools investigator responder tools-fake investigator-fake responder-fake deploy-agentcore invoke-agentcore deploy-apprunner test-e2e-apprunner dev

STARTER_REPO := $(abspath ../Research-Assistant)

help:  ## Show Project 2 run targets
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "}; {printf "  %-18s %s\n", $$1, $$2}'

install:  ## Install dependencies (uv sync)
	uv sync

postgres-up:  ## Start local pgvector Postgres (Docker, port 5433)
	cd $(STARTER_REPO) && docker compose up -d postgres

ingest-runbooks: postgres-up  ## Ingest runbooks into pgvector (uses monk-ticket-triage/.env)
	uv run python scripts/ingest_runbooks.py

seed-past-cases: postgres-up  ## Seed past_resolutions table for episodic memory
	uv run python scripts/seed_past_resolutions.py

graph:  ## Run sample ticket through the supervisor graph (real model from .env)
	uv run python -m app.graph

triager:  ## Run triager only on the sample ticket (real model from .env)
	uv run python -c "from app.agents.triager import triager_node; from app.graph import sample_ticket; print(triager_node(sample_ticket()))"

tools:  ## Smoke-test all four investigator tools (real model + Postgres from .env)
	uv run python -c "from app.tools._domain import set_domain; from app.tools import query_logs, query_metrics, search_runbooks, get_ticket_history; set_domain('it-helpdesk'); print('logs:', query_logs.invoke({'service': 'vpn-gateway', 'since': '1h'})); print('metrics:', query_metrics.invoke({'service': 'vpn-gateway', 'metric': 'connection_errors'})); print('runbooks:', search_runbooks.invoke({'query': 'VPN hangs connecting', 'k': 1})); print('history:', get_ticket_history.invoke({'user_id': 'alex@example.com', 'k': 2}))"

investigator:  ## Run investigator on a pre-classified sample ticket (real model from .env)
	uv run python -c "from app.agents.investigator import investigator_node; from app.agents.triager import triager_node; from app.graph import sample_ticket; s=sample_ticket(); s.update(triager_node(s)); print(investigator_node(s))"

responder:  ## Run responder after triage + investigation on sample ticket
	uv run python -c "from app.agents.investigator import investigator_node; from app.agents.responder import responder_node; from app.agents.triager import triager_node; from app.graph import sample_ticket; s=sample_ticket(); s.update(triager_node(s)); s.update(investigator_node(s)); print(responder_node(s))"

tools-fake:  ## Offline tool smoke-test (MONK_MODEL=fake)
	MONK_MODEL=fake MONK_EMBEDDINGS=fake $(MAKE) tools

investigator-fake:  ## Offline investigator test (MONK_MODEL=fake)
	MONK_MODEL=fake MONK_EMBEDDINGS=fake $(MAKE) investigator

responder-fake:  ## Offline responder test (MONK_MODEL=fake)
	MONK_MODEL=fake MONK_EMBEDDINGS=fake $(MAKE) responder

dev:  ## Start approval API + UI on :8001
	uv run uvicorn app.main:app --host 0.0.0.0 --port 8001

deploy-agentcore:  ## Deploy to AWS Bedrock AgentCore (needs POSTGRES_DSN_CLOUDSQL_DIRECT in .env)
	./deploy/deploy_agentcore.sh

invoke-agentcore:  ## Invoke deployed AgentCore agent with sample ticket
	./deploy/test_invoke.sh

deploy-apprunner:  ## Deploy approval UI to AWS App Runner
	./deploy/deploy_apprunner.sh

test-e2e-apprunner:  ## E2E test against deployed App Runner (URL=https://... make test-e2e-apprunner)
	@test -n "$(URL)" || (echo "Usage: URL=https://your-service.awsapprunner.com make test-e2e-apprunner" && exit 1)
	./deploy/test_e2e_apprunner.sh "$(URL)"
