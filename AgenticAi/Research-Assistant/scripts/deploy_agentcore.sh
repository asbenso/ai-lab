#!/usr/bin/env bash
# Monk Technologies - deploy Project 2 (Ticket Triage) to AWS Bedrock AgentCore.
# Delegates to monk-ticket-triage/deploy/deploy_agentcore.sh.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../../monk-ticket-triage/deploy/deploy_agentcore.sh" "$@"
