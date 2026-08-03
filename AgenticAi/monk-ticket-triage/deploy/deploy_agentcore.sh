#!/usr/bin/env bash
# Monk Technologies - deploy Project 2 (Ticket Triage) to AWS Bedrock AgentCore.
# Idempotent: safe to re-run configure + deploy.

set -euo pipefail

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
ok()    { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn()  { printf "  \033[33m!!\033[0m %s\n" "$*"; }
err()   { printf "  \033[31m✗\033[0m %s\n" "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    ENV_FILE="$PROJECT_DIR/../Research-Assistant/.env"
fi

cd "$PROJECT_DIR"

# Load .env line-by-line (DSNs contain ?, =, : that break `source`).
if [[ -f "$ENV_FILE" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        key="${line%%=*}"
        value="${line#*=}"
        export "$key=$value"
    done < "$ENV_FILE"
    ok "Loaded $(basename "$ENV_FILE")"
fi

NAME="${AGENT_NAME:-monk_ticket_triage}"
ENTRYPOINT="${ENTRYPOINT:-deploy/agentcore_entrypoint.py}"
REGION="${AWS_REGION:-us-east-1}"
export AGENTCORE_SUPPRESS_RECOMMENDATION=1

# Cloud runtime cannot reach localhost Postgres — prefer the Cloud SQL direct DSN.
if [[ -n "${POSTGRES_DSN_CLOUDSQL_DIRECT:-}" ]]; then
    export POSTGRES_DSN="$POSTGRES_DSN_CLOUDSQL_DIRECT"
elif [[ "${POSTGRES_DSN:-}" == *localhost* || "${POSTGRES_DSN:-}" == *127.0.0.1* ]]; then
    err "POSTGRES_DSN points to localhost; AgentCore in AWS cannot reach it."
    echo "  Set POSTGRES_DSN_CLOUDSQL_DIRECT in monk-ticket-triage/.env, or export before deploy:"
    echo "  export POSTGRES_DSN_CLOUDSQL_DIRECT='postgresql://postgres:<pass>@34.93.253.191:5432/monk'"
    echo "  Authorize Cloud SQL for AgentCore egress first (see create_cloudsql.sh)."
    exit 1
fi

# Fail fast if Cloud SQL is unreachable from the runtime.
if [[ "$POSTGRES_DSN" == *"?"* ]]; then
    export POSTGRES_DSN="${POSTGRES_DSN}&connect_timeout=15"
else
    export POSTGRES_DSN="${POSTGRES_DSN}?connect_timeout=15"
fi

bold "Monk Technologies — deploy $NAME to AWS Bedrock AgentCore"
echo "  region=$REGION  entrypoint=$ENTRYPOINT"
echo "  postgres=${POSTGRES_DSN%%@*}@***"
echo

if ! command -v uv >/dev/null 2>&1; then
    err "uv is required but not installed."
    exit 1
fi

if ! uv run agentcore --help >/dev/null 2>&1; then
    warn "Installing bedrock-agentcore-starter-toolkit..."
    uv pip install bedrock-agentcore bedrock-agentcore-starter-toolkit
fi

# Runtime env vars forwarded to the cloud agent.
DEPLOY_ENV_KEYS=(
    POSTGRES_DSN
    MONK_MODEL
    MONK_EMBEDDINGS
    MONK_MEMORY
    AWS_REGION
    LANGSMITH_API_KEY
    LANGSMITH_PROJECT
    LANGSMITH_TRACING
    LANGCHAIN_TRACING_V2
    LANGSMITH_ENDPOINT
)

ENV_ARGS=()
for key in "${DEPLOY_ENV_KEYS[@]}"; do
    value="${!key:-}"
    if [[ -n "$value" ]]; then
        ENV_ARGS+=(--env "${key}=${value}")
    fi
done

bold "1. Configure"
uv run agentcore configure \
    --name "$NAME" \
    --entrypoint "$ENTRYPOINT" \
    --deployment-type direct_code_deploy \
    --runtime PYTHON_3_11 \
    --region "$REGION" \
    --non-interactive \
    --disable-memory \
    --idle-timeout 600 \
    --max-lifetime 28800

bold "2. Deploy"
uv run agentcore deploy --agent "$NAME" "${ENV_ARGS[@]}"

bold "Done."
echo "  Status:  uv run agentcore status --agent $NAME"
echo "  Logs:    uv run agentcore logs --agent $NAME --follow"
echo "  Invoke:  uv run agentcore invoke --agent $NAME --payload '{\"ticket_id\":\"TCK-1001\", ...}'"
