# AgenticAi workspace — Project 1 + Project 2
PROJECT := Research-Assistant
P2_PROJECT := monk-ticket-triage

.PHONY: help install smoke tools tools-trace tracing-check search-local-docs \
        web-search fetch-url summarize p2-graph p2-triager p2-install

help:  ## Show available targets
	@$(MAKE) -C $(PROJECT) help

install:  ## Install dependencies via uv
	@$(MAKE) -C $(PROJECT) install

smoke:  ## Run Bedrock + Vertex + Postgres smoke test
	@$(MAKE) -C $(PROJECT) smoke

web-search:  ## Smoke test web_search tool
	@$(MAKE) -C $(PROJECT) web-search

fetch-url:  ## Smoke test fetch_url tool
	@$(MAKE) -C $(PROJECT) fetch-url

summarize:  ## Smoke test summarize tool
	@$(MAKE) -C $(PROJECT) summarize

tools:  ## Run all Project 1 tool smoke tests
	@$(MAKE) -C $(PROJECT) tools

tools-trace:  ## Tool smoke tests with LangSmith tracing (MONK_TRACE_SMOKE=1)
	@$(MAKE) -C $(PROJECT) tools-trace

search-local-docs:  ## Smoke test pgvector retrieval
	@$(MAKE) -C $(PROJECT) search-local-docs

tracing-check:  ## Verify LangSmith API key and endpoint
	@$(MAKE) -C $(PROJECT) tracing-check

p2-install:  ## Install Project 2 (ticket triage) dependencies
	@$(MAKE) -C $(P2_PROJECT) install

p2-graph:  ## Run Project 2 sample ticket graph demo
	@$(MAKE) -C $(P2_PROJECT) graph

p2-triager:  ## Run Project 2 triager on sample ticket only
	@$(MAKE) -C $(P2_PROJECT) triager
