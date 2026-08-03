#!/usr/bin/env bash
# Invoke the deployed monk_ticket_triage AgentCore agent with the sample ticket.
set -euo pipefail

cd "$(dirname "$0")/.."
export AGENTCORE_SUPPRESS_RECOMMENDATION=1

PAYLOAD="$(cat deploy/sample_invoke.json)"
uv run agentcore invoke --agent monk_ticket_triage "$PAYLOAD"
