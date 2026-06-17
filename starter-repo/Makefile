.PHONY: help install smoke ingest dev eval lint format clean \
        setup-aws setup-gcp deploy-cloudrun deploy-agentcore deploy-vertex \
        tools tools-trace tracing-check search-local-docs web-search fetch-url summarize

help:  ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "Targets:\n"} /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

install:  ## Install dependencies via uv
	uv sync

smoke:  ## Run the smoke test against Bedrock + Vertex
	uv run python -m app.smoke

web-search:  ## Smoke test web_search tool
	uv run python -m app.tools.web_search

fetch-url:  ## Smoke test fetch_url tool
	uv run python -m app.tools.fetch_url

summarize:  ## Smoke test summarize tool
	uv run python -m app.tools.summarize

tools:  ## Run Project 1 tool smoke test (web + local docs + fetch + summarize)
	uv run python -m app.tools

tools-trace:  ## Same as tools, but send runs to LangSmith (MONK_TRACE_SMOKE=1)
	MONK_TRACE_SMOKE=1 uv run python -m app.tools

search-local-docs:  ## Smoke test pgvector retrieval (requires postgres + ingest)
	uv run python -m app.tools.search_local_docs

tracing-check:  ## Verify LangSmith API key and endpoint
	uv run python -m app.tracing_check

ingest:  ## Ingest a sample corpus, e.g. make ingest CORPUS=aws-docs
	@test -n "$(CORPUS)" || (echo "Usage: make ingest CORPUS=<aws-docs|k8s-docs|anthropic-policy>" && exit 1)
	uv run python -m ingest.upsert --corpus data/sample-corpus/$(CORPUS) --table docs

dev:  ## Run the FastAPI app locally with reload
	uv run uvicorn app.main:app --reload --port 8000

eval:  ## Run all available evals
	uv run python -m evals.run_all

lint:  ## Lint with ruff
	uv run ruff check .

format:  ## Format with ruff
	uv run ruff format .

clean:  ## Remove caches and __pycache__
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache

setup-aws:  ## Verify AWS CLI + Bedrock gpt-oss access
	./scripts/setup_aws.sh

setup-gcp:  ## Verify gcloud + Vertex AI access
	./scripts/setup_gcp.sh

deploy-cloudrun:  ## Deploy Project 1 to Google Cloud Run
	./scripts/deploy_cloudrun.sh

deploy-agentcore:  ## Deploy Project 2 to AWS Bedrock AgentCore
	./scripts/deploy_agentcore.sh

deploy-vertex:  ## Deploy Project 2 to GCP Vertex AI Agent Engine
	./scripts/deploy_vertex_engine.sh
