# Git root wrapper — Python project lives in starter-repo/
PROJECT := starter-repo

.PHONY: help install smoke tools tools-trace tracing-check search-local-docs

help:  ## Show available targets (runs inside $(PROJECT)/)
	@$(MAKE) -C $(PROJECT) help

install:  ## Install dependencies via uv
	@$(MAKE) -C $(PROJECT) install

smoke:  ## Run Bedrock + Vertex + Postgres smoke test
	@$(MAKE) -C $(PROJECT) smoke

tools:  ## Run Project 1 tool smoke test (search -> fetch -> summarize)
	@$(MAKE) -C $(PROJECT) tools

tools-trace:  ## Tool smoke test with LangSmith tracing enabled
	@$(MAKE) -C $(PROJECT) tools-trace

search-local-docs:  ## Smoke test pgvector retrieval (requires postgres + ingest)
	@$(MAKE) -C $(PROJECT) search-local-docs

tracing-check:  ## Verify LangSmith API key and endpoint
	@$(MAKE) -C $(PROJECT) tracing-check
