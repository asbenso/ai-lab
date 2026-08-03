#!/usr/bin/env bash
# Monk Technologies - deploy Project 1 (Research Assistant) to Google Cloud Run.
# Idempotent: APIs, secrets, IAM, and the service itself are all safe to re-create.

set -euo pipefail

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
ok()    { printf "  \033[32m✓\033[0m %s\n" "$*"; }
skip()  { printf "  \033[33m»\033[0m %s\n" "$*"; }
warn()  { printf "  \033[33m!!\033[0m %s\n" "$*"; }
err()   { printf "  \033[31m✗\033[0m %s\n" "$*" >&2; }

PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
    err "No default GCP project. Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

SERVICE="${SERVICE:-monk-research-assistant}"
REGION="${REGION:-asia-south1}"
CLOUDSQL_INSTANCE="${CLOUDSQL_INSTANCE:-monk-postgres}"
CONNECTION_NAME="${PROJECT}:${REGION}:${CLOUDSQL_INSTANCE}"

# .env loader. Do NOT use `source` — DSN values contain ?, =, :, & which the shell
# would interpret as syntax.
if [[ -f .env ]]; then
    while IFS= read -r line; do
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$line" || ! "$line" == *=* ]] && continue
        key="${line%%=*}"
        value="${line#*=}"
        export "$key=$value"
    done < .env
fi

bold "Monk Technologies — deploy $SERVICE to Cloud Run"
echo "  project=$PROJECT  region=$REGION  service=$SERVICE"
echo "  cloud sql=$CONNECTION_NAME"
echo

# ---------------------------------------------------------------------------
bold "Step 1 — Enable required APIs"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    sqladmin.googleapis.com \
    aiplatform.googleapis.com \
    --project "$PROJECT" --quiet
ok "APIs enabled (run, cloudbuild, artifactregistry, secretmanager, sqladmin, aiplatform)"
echo

# ---------------------------------------------------------------------------
bold "Step 2 — Push secrets to Secret Manager"
push_secret() {
    local name="$1" value="$2"
    if [[ -z "$value" ]]; then
        err "Secret '$name' has no value — set the corresponding key in .env"
        exit 1
    fi
    if gcloud secrets describe "$name" --project "$PROJECT" >/dev/null 2>&1; then
        skip "secret $name already exists"
    else
        printf "%s" "$value" \
            | gcloud secrets create "$name" \
                --replication-policy=automatic \
                --data-file=- \
                --project "$PROJECT" --quiet
        ok "created secret $name"
    fi
}

push_secret monk-postgres-dsn "${POSTGRES_DSN:-}"
push_secret monk-tavily       "${TAVILY_API_KEY:-}"
push_secret monk-langsmith    "${LANGSMITH_API_KEY:-}"
echo

# ---------------------------------------------------------------------------
bold "Step 3 — Grant IAM roles to Compute Engine default service account"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')"
SA_EMAIL="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
echo "  service account: $SA_EMAIL"

# Per-secret accessor binding so Cloud Run can read each secret at runtime.
for secret in monk-postgres-dsn monk-tavily monk-langsmith; do
    gcloud secrets add-iam-policy-binding "$secret" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="roles/secretmanager.secretAccessor" \
        --project "$PROJECT" --quiet &>/dev/null || true
    ok "secretmanager.secretAccessor on $secret"
done

# Project-level bindings for Cloud Build + Vertex AI.
for role in \
    roles/storage.objectViewer \
    roles/cloudbuild.builds.builder \
    roles/artifactregistry.writer \
    roles/aiplatform.user; do
    gcloud projects add-iam-policy-binding "$PROJECT" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="$role" \
        --quiet &>/dev/null || true
    ok "$role on project"
done
echo

# ---------------------------------------------------------------------------
bold "Step 4 — Deploy to Cloud Run"
gcloud run deploy "$SERVICE" \
    --source . \
    --project "$PROJECT" \
    --region "$REGION" \
    --allow-unauthenticated \
    --add-cloudsql-instances "$CONNECTION_NAME" \
    --set-env-vars "MONK_MODEL=google_vertexai:gemini-2.5-pro,MONK_EMBEDDINGS=google_vertexai:text-embedding-005,LANGSMITH_PROJECT=$SERVICE,LANGSMITH_TRACING=true,GCP_PROJECT=$PROJECT,GCP_LOCATION=us-central1" \
    --set-secrets "POSTGRES_DSN=monk-postgres-dsn:latest,TAVILY_API_KEY=monk-tavily:latest,LANGSMITH_API_KEY=monk-langsmith:latest" \
    --memory 1Gi \
    --cpu 1 \
    --timeout 600 \
    --concurrency 4
echo

URL="$(gcloud run services describe "$SERVICE" \
    --project "$PROJECT" \
    --region "$REGION" \
    --format='value(status.url)')"

bold "Deployed."
echo "  $URL"
echo
echo "Quick smoke test:"
echo "  curl -fsS $URL/health    # /healthz is intercepted by Google Frontend on .run.app"
