#!/usr/bin/env bash
# Monk Technologies - guided AWS setup for the bootcamp.
# Run once before Day 1. Re-running is safe.

set -euo pipefail

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32mok\033[0m %s\n" "$*"; }
warn() { printf "  \033[33m!!\033[0m %s\n" "$*"; }
err()  { printf "  \033[31mERR\033[0m %s\n" "$*"; }

bold "Monk Technologies - AWS setup check"
echo

# 1. aws CLI installed?
bold "1. aws CLI"
if ! command -v aws >/dev/null 2>&1; then
    err "aws CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi
ok "$(aws --version 2>&1)"
echo

# 2. credentials configured?
bold "2. AWS credentials"
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    err "AWS credentials not configured. Run: aws configure"
    err "You need an Access Key ID and Secret. Region: us-east-1 is fine for the bootcamp."
    exit 1
fi
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
USER_ARN=$(aws sts get-caller-identity --query Arn --output text)
ok "account=$ACCOUNT_ID arn=$USER_ARN"
echo

# 3. region
bold "3. AWS region"
REGION=$(aws configure get region || echo "")
if [[ -z "$REGION" ]]; then
    warn "No default region set. Setting to us-east-1."
    aws configure set region us-east-1
    REGION=us-east-1
fi
if [[ "$REGION" != "us-east-1" && "$REGION" != "us-east-2" && "$REGION" != "us-west-2" ]]; then
    warn "Region is $REGION. gpt-oss-120b is most reliably available in us-east-1 / us-east-2 / us-west-2."
fi
ok "region=$REGION"
echo

# 4. Bedrock model access
bold "4. Bedrock model access"
echo "  Probing the models we use in the bootcamp..."

# Chat model probe uses the Converse API.
check_chat_model() {
    local model_id="$1"
    local label="$2"
    if aws bedrock-runtime converse \
        --model-id "$model_id" \
        --messages '[{"role":"user","content":[{"text":"hi"}]}]' \
        --inference-config '{"maxTokens":1}' \
        --region "$REGION" >/dev/null 2>&1; then
        ok "$label  ($model_id)"
    else
        warn "$label is not callable. Either model access is pending or the model isn't in $REGION."
        warn "  Console: https://console.aws.amazon.com/bedrock/home?region=$REGION#/modelaccess"
    fi
}

# Embedding probe uses invoke-model - embedding models don't speak Converse.
check_embedding_model() {
    local model_id="$1"
    local label="$2"
    local tmp
    tmp=$(mktemp)
    if aws bedrock-runtime invoke-model \
        --model-id "$model_id" \
        --cli-binary-format raw-in-base64-out \
        --body '{"inputText":"hi"}' \
        --content-type application/json \
        --accept application/json \
        --region "$REGION" \
        "$tmp" >/dev/null 2>&1; then
        ok "$label  ($model_id)"
    else
        warn "$label is not callable. Either model access is pending or the model isn't in $REGION."
        warn "  Console: https://console.aws.amazon.com/bedrock/home?region=$REGION#/modelaccess"
    fi
    rm -f "$tmp"
}

# Direct in-region model IDs - gpt-oss does NOT require the `us.` inference-profile
# prefix that Claude 4.x needs. No Anthropic-style use-case form either.
check_chat_model "openai.gpt-oss-120b-1:0" "OpenAI gpt-oss-120b"
check_chat_model "openai.gpt-oss-20b-1:0" "OpenAI gpt-oss-20b (fallback)"
check_embedding_model "amazon.titan-embed-text-v2:0" "Titan Embeddings V2"
echo

bold "Done."
echo "If any model shows a warning, open the Bedrock console and request access:"
echo "  https://console.aws.amazon.com/bedrock/home?region=$REGION#/modelaccess"
