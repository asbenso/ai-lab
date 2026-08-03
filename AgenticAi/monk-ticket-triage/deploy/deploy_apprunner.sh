#!/usr/bin/env bash
# Monk Technologies - deploy Project 2 approval UI to AWS App Runner.
# Idempotent: safe to re-run (builds image, updates or creates service).

set -euo pipefail

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
ok()    { printf "  \033[32m✓\033[0m %s\n" "$*"; }
warn()  { printf "  \033[33m!!\033[0m %s\n" "$*"; }
err()   { printf "  \033[31m✗\033[0m %s\n" "$*" >&2; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    ENV_FILE="$PROJECT_DIR/../Research-Assistant/.env"
fi

cd "$PROJECT_DIR"

if [[ -f "$ENV_FILE" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        key="${line%%=*}"
        value="${line#*=}"
        export "$key=$value"
    done < "$ENV_FILE"
    ok "Loaded $(basename "$ENV_FILE")"
fi

SERVICE="${APPRUNNER_SERVICE:-monk-ticket-triage-ui}"
REGION="${AWS_REGION:-us-east-1}"
REPO="${ECR_REPO:-monk-ticket-triage-ui}"

if [[ -n "${POSTGRES_DSN_CLOUDSQL_DIRECT:-}" ]]; then
    export POSTGRES_DSN="$POSTGRES_DSN_CLOUDSQL_DIRECT"
elif [[ "${POSTGRES_DSN:-}" == *localhost* || "${POSTGRES_DSN:-}" == *127.0.0.1* ]]; then
    err "POSTGRES_DSN points to localhost; App Runner cannot reach it."
    echo "  Set POSTGRES_DSN_CLOUDSQL_DIRECT in monk-ticket-triage/.env"
    exit 1
fi

if [[ "$POSTGRES_DSN" == *"?"* ]]; then
    export POSTGRES_DSN="${POSTGRES_DSN}&connect_timeout=15"
else
    export POSTGRES_DSN="${POSTGRES_DSN}?connect_timeout=15"
fi

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${REPO}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE="${ECR_URI}:${IMAGE_TAG}"

bold "Monk Technologies — deploy $SERVICE to AWS App Runner"
echo "  region=$REGION  account=$ACCOUNT_ID"
echo "  image=$IMAGE"
echo

if ! command -v docker >/dev/null 2>&1; then
    err "docker is required to build the container image."
    exit 1
fi

bold "1. ECR repository"
if aws ecr describe-repositories --repository-names "$REPO" --region "$REGION" >/dev/null 2>&1; then
    ok "Repository $REPO exists"
else
    aws ecr create-repository --repository-name "$REPO" --region "$REGION" >/dev/null
    ok "Created repository $REPO"
fi

bold "2. Build and push image"
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com"
docker build -t "$IMAGE" .
docker push "$IMAGE"
ok "Pushed $IMAGE"

bold "3. IAM roles"
ECR_ACCESS_ROLE="${APPRUNNER_ECR_ACCESS_ROLE:-AppRunnerECRAccessRole}"
INSTANCE_ROLE="${APPRUNNER_INSTANCE_ROLE:-MonkTicketTriageAppRunnerRole}"

ensure_role() {
    local role_name="$1"
    local trust_service="$2"
    if aws iam get-role --role-name "$role_name" >/dev/null 2>&1; then
        ok "Role $role_name exists"
    else
        aws iam create-role \
            --role-name "$role_name" \
            --assume-role-policy-document "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"${trust_service}\"},\"Action\":\"sts:AssumeRole\"}]}" \
            >/dev/null
        ok "Created role $role_name"
    fi
}

ensure_role "$ECR_ACCESS_ROLE" "build.apprunner.amazonaws.com"
aws iam attach-role-policy \
    --role-name "$ECR_ACCESS_ROLE" \
    --policy-arn arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess \
    >/dev/null 2>&1 || true

ensure_role "$INSTANCE_ROLE" "tasks.apprunner.amazonaws.com"
BEDROCK_POLICY='{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:ApplyGuardrail"],
    "Resource": "*"
  }]
}'
aws iam put-role-policy \
    --role-name "$INSTANCE_ROLE" \
    --policy-name MonkBedrockInvoke \
    --policy-document "$BEDROCK_POLICY" \
    >/dev/null
ok "Bedrock invoke policy on $INSTANCE_ROLE"

ECR_ACCESS_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ECR_ACCESS_ROLE}"
INSTANCE_ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${INSTANCE_ROLE}"

AUTOSCALING_NAME="${APPRUNNER_AUTOSCALING:-monk-ticket-triage-ui-as}"
AUTOSCALING_ARN="$(aws apprunner list-auto-scaling-configurations --region "$REGION" \
    --query "AutoScalingConfigurationSummaryList[?AutoScalingConfigurationName=='${AUTOSCALING_NAME}'].AutoScalingConfigurationArn | [0]" \
    --output text 2>/dev/null || true)"
if [[ -z "$AUTOSCALING_ARN" || "$AUTOSCALING_ARN" == "None" ]]; then
    AUTOSCALING_ARN="$(aws apprunner create-auto-scaling-configuration \
        --region "$REGION" \
        --auto-scaling-configuration-name "$AUTOSCALING_NAME" \
        --max-concurrency 1 \
        --min-size 1 \
        --max-size 1 \
        --query AutoScalingConfiguration.AutoScalingConfigurationArn \
        --output text)"
    ok "Created auto scaling config $AUTOSCALING_NAME (max 1 instance)"
else
    ok "Using auto scaling config $AUTOSCALING_NAME"
fi

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

python3 - "$TMPDIR" "$IMAGE" "$ECR_ACCESS_ARN" "$INSTANCE_ROLE_ARN" <<'PY'
import json, os, sys
out_dir, image, ecr_access_arn, instance_role_arn = sys.argv[1:5]
keys = [
    "POSTGRES_DSN", "MONK_MODEL", "MONK_EMBEDDINGS", "MONK_MEMORY",
    "MONK_CHECKPOINT", "AWS_REGION", "AWS_DEFAULT_REGION",
    "LANGSMITH_API_KEY", "LANGSMITH_PROJECT", "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING_V2", "LANGSMITH_ENDPOINT",
]
env = {
    "MONK_CHECKPOINT": "postgres",
    "MONK_MEMORY": "postgres",
    "AWS_DEFAULT_REGION": os.environ.get("AWS_REGION", "us-east-1"),
}
for k in keys:
    v = os.environ.get(k)
    if v:
        env[k] = v
source = {
    "ImageRepository": {
        "ImageIdentifier": image,
        "ImageRepositoryType": "ECR",
        "ImageConfiguration": {
            "Port": "8080",
            "RuntimeEnvironmentVariables": env,
        },
    },
    "AutoDeploymentsEnabled": False,
    "AuthenticationConfiguration": {"AccessRoleArn": ecr_access_arn},
}
instance = {"Cpu": "1024", "Memory": "2048", "InstanceRoleArn": instance_role_arn}
health = {
    "Protocol": "HTTP",
    "Path": "/health",
    "Interval": 10,
    "Timeout": 5,
    "HealthyThreshold": 1,
    "UnhealthyThreshold": 5,
}
for name, obj in ("source", source), ("instance", instance), ("health", health):
    with open(os.path.join(out_dir, f"{name}.json"), "w") as f:
        json.dump(obj, f)
PY

SOURCE_CONFIG="file://${TMPDIR}/source.json"
INSTANCE_CONFIG="file://${TMPDIR}/instance.json"
HEALTH_CONFIG="file://${TMPDIR}/health.json"

wait_for_service() {
    local label="$1"
    local status=""
    for _ in $(seq 1 60); do
        status="$(aws apprunner describe-service --region "$REGION" --service-arn "$SERVICE_ARN" \
            --query 'Service.Status' --output text)"
        if [[ "$status" == "RUNNING" ]]; then
            ok "$label"
            return 0
        fi
        if [[ "$status" == *"FAILED"* ]]; then
            err "Service status: $status"
            exit 1
        fi
        sleep 10
    done
    err "Timed out waiting for service (status=$status)"
    exit 1
}

bold "4. App Runner service"
SERVICE_ARN="$(aws apprunner list-services --region "$REGION" \
    --query "ServiceSummaryList[?ServiceName=='${SERVICE}'].ServiceArn | [0]" --output text)"

if [[ -z "$SERVICE_ARN" || "$SERVICE_ARN" == "None" ]]; then
    SERVICE_ARN="$(aws apprunner create-service \
        --region "$REGION" \
        --service-name "$SERVICE" \
        --source-configuration "$SOURCE_CONFIG" \
        --instance-configuration "$INSTANCE_CONFIG" \
        --health-check-configuration "$HEALTH_CONFIG" \
        --auto-scaling-configuration-arn "$AUTOSCALING_ARN" \
        --query Service.ServiceArn --output text)"
    ok "Created service $SERVICE"
else
    aws apprunner update-service \
        --region "$REGION" \
        --service-arn "$SERVICE_ARN" \
        --source-configuration "$SOURCE_CONFIG" \
        --instance-configuration "$INSTANCE_CONFIG" \
        --health-check-configuration "$HEALTH_CONFIG" \
        --auto-scaling-configuration-arn "$AUTOSCALING_ARN" \
        >/dev/null
    ok "Updated service $SERVICE"
    wait_for_service "Service ready after update"
    aws apprunner start-deployment --region "$REGION" --service-arn "$SERVICE_ARN" >/dev/null
    ok "Started new deployment"
fi

bold "5. Wait for service to be running"
wait_for_service "Deployment complete"

URL="$(aws apprunner describe-service --region "$REGION" --service-arn "$SERVICE_ARN" \
    --query 'Service.ServiceUrl' --output text)"

bold "Deployed."
echo "  https://${URL}"
echo
echo "Open approval UI:  https://${URL}/"
echo "Health check:      curl -fsS https://${URL}/health"
echo "E2E smoke test:    ./deploy/test_e2e_apprunner.sh https://${URL}"
