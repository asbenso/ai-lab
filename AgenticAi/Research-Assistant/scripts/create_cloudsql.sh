#!/usr/bin/env bash
# Monk Technologies - provision a minimal Cloud SQL Postgres 15 + pgvector instance.
# Idempotent: safe to re-run. Use --delete to tear down.

set -euo pipefail

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
ok()    { printf "  \033[32mok\033[0m %s\n" "$*"; }
skip()  { printf "  \033[33m>>\033[0m %s\n" "$*"; }
warn()  { printf "  \033[33m!!\033[0m %s\n" "$*"; }
err()   { printf "  \033[31mERR\033[0m %s\n" "$*" >&2; }

find_gcloud() {
    if [[ -n "${GCLOUD_BIN:-}" && -x "$GCLOUD_BIN" ]]; then
        printf '%s\n' "$GCLOUD_BIN"
        return 0
    fi
    local resolved
    resolved="$(type -P gcloud 2>/dev/null || true)"
    if [[ -n "$resolved" && -x "$resolved" ]]; then
        printf '%s\n' "$resolved"
        return 0
    fi
    local candidate
    for candidate in \
        "${CLOUDSDK_ROOT:-}/bin/gcloud" \
        "$HOME/google-cloud-sdk/bin/gcloud" \
        "/usr/lib/google-cloud-sdk/bin/gcloud" \
        "/opt/google-cloud-sdk/bin/gcloud" \
        "/snap/bin/gcloud" \
        "/home/linuxbrew/.linuxbrew/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/bin/gcloud"; do
        if [[ -n "$candidate" && -x "$candidate" ]]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

install_gcloud_user_local() {
    local arch tarball url dest
    arch="$(uname -m)"
    case "$arch" in
        x86_64) tarball="google-cloud-cli-linux-x86_64.tar.gz" ;;
        aarch64|arm64) tarball="google-cloud-cli-linux-arm.tar.gz" ;;
        *)
            err "Unsupported architecture for auto-install: $arch"
            return 1
            ;;
    esac
    url="https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/${tarball}"
    dest="$HOME/google-cloud-sdk"
    warn "gcloud not found — installing Google Cloud SDK to $dest"
    curl -fsSL "$url" -o "/tmp/${tarball}"
    rm -rf "$dest"
    tar -xzf "/tmp/${tarball}" -C "$HOME"
    "$dest/install.sh" --quiet --path-update false --command-completion false
    ok "installed Google Cloud SDK"
    printf '%s/bin/gcloud\n' "$dest"
}

ensure_gcloud() {
    local bin
    if bin="$(find_gcloud)"; then
        export PATH="$(dirname "$bin"):$PATH"
        return 0
    fi
    if [[ "${INSTALL_GCLOUD:-0}" -eq 1 ]]; then
        bin="$(install_gcloud_user_local)"
        export PATH="$(dirname "$bin"):$PATH"
        return 0
    fi
    err "gcloud CLI not found."
    err "Install one of:"
    err "  INSTALL_GCLOUD=1 ./scripts/create_cloudsql.sh     # user-local SDK (no sudo)"
    err "  sudo snap install google-cloud-cli --classic     # snap (Ubuntu)"
    err "  https://cloud.google.com/sdk/docs/install"
    return 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_SQL="${SCRIPT_DIR}/postgres-init.sql"

CLOUDSQL_INSTANCE="${CLOUDSQL_INSTANCE:-monk-postgres}"
REGION="${REGION:-asia-south1}"
DB_NAME="${DB_NAME:-monk}"
DB_USER="${DB_USER:-postgres}"

DELETE_MODE=0
INSTALL_GCLOUD=0
for arg in "$@"; do
    case "$arg" in
        --delete) DELETE_MODE=1 ;;
        --install-gcloud) INSTALL_GCLOUD=1 ;;
        -h|--help)
            cat <<'EOF'
Usage: scripts/create_cloudsql.sh [--delete] [--install-gcloud]

Provision (or tear down) a minimal Cloud SQL PostgreSQL 15 instance with pgvector.

Flags:
  --delete            Delete the Cloud SQL instance
  --install-gcloud    Install Google Cloud SDK to ~/google-cloud-sdk if missing

Environment overrides:
  CLOUDSQL_INSTANCE   Instance id (default: monk-postgres)
  REGION              GCP region (default: asia-south1)
  DB_NAME             Database name (default: monk)
  DB_PASS             Postgres password (default: random 24-char string)
  DB_USER             Postgres user (default: postgres)
  INSTALL_GCLOUD=1    Same as --install-gcloud
  GCLOUD_BIN          Path to gcloud binary (optional)

PROJECT is read from: gcloud config get-value project
EOF
            exit 0
            ;;
        *)
            err "Unknown argument: $arg (try --help)"
            exit 1
            ;;
    esac
done

ensure_gcloud

PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
    err "No default GCP project. Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

if [[ ! -f "$INIT_SQL" ]]; then
    err "Missing init SQL: $INIT_SQL"
    exit 1
fi

if [[ -z "${DB_PASS:-}" ]]; then
    DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
fi

CONNECTION_NAME="${PROJECT}:${REGION}:${CLOUDSQL_INSTANCE}"

if [[ "$DELETE_MODE" -eq 1 ]]; then
    bold "Delete Cloud SQL instance"
    echo "  project=$PROJECT  instance=$CLOUDSQL_INSTANCE  region=$REGION"
    echo
    if gcloud sql instances describe "$CLOUDSQL_INSTANCE" --project="$PROJECT" >/dev/null 2>&1; then
        gcloud sql instances delete "$CLOUDSQL_INSTANCE" --project="$PROJECT" --quiet
        ok "deleted $CLOUDSQL_INSTANCE"
    else
        skip "instance $CLOUDSQL_INSTANCE does not exist"
    fi
    exit 0
fi

bold "Monk Technologies - Cloud SQL (Postgres 15 + pgvector)"
echo "  project=$PROJECT  instance=$CLOUDSQL_INSTANCE  region=$REGION  db=$DB_NAME"
echo

wait_instance_runnable() {
    local state
    while true; do
        state="$(gcloud sql instances describe "$CLOUDSQL_INSTANCE" \
            --project="$PROJECT" \
            --format='value(state)' 2>/dev/null || echo "MISSING")"
        if [[ "$state" == "RUNNABLE" ]]; then
            return 0
        fi
        if [[ "$state" == "FAILED" ]]; then
            err "instance entered FAILED state"
            exit 1
        fi
        sleep 5
    done
}

wait_operation() {
    local op="$1"
    if [[ -n "$op" ]]; then
        gcloud sql operations wait "$op" --project="$PROJECT" --timeout=600 >/dev/null
    fi
}

# ---------------------------------------------------------------------------
bold "Step 0 — Enable Cloud SQL Admin API"
if gcloud services list --enabled --project="$PROJECT" --format='value(name)' \
    | grep -q '^sqladmin\.googleapis\.com$'; then
    skip "sqladmin.googleapis.com already enabled"
else
    gcloud services enable sqladmin.googleapis.com --project="$PROJECT" --quiet
    ok "enabled sqladmin.googleapis.com"
fi
echo

# ---------------------------------------------------------------------------
bold "Step 1 — Cloud SQL instance (db-f1-micro, Postgres 15)"
if gcloud sql instances describe "$CLOUDSQL_INSTANCE" --project="$PROJECT" >/dev/null 2>&1; then
    skip "instance $CLOUDSQL_INSTANCE already exists"
    gcloud sql users set-password "$DB_USER" \
        --instance="$CLOUDSQL_INSTANCE" \
        --project="$PROJECT" \
        --password="$DB_PASS" \
        --quiet
    ok "reset password for user $DB_USER"
else
    gcloud sql instances create "$CLOUDSQL_INSTANCE" \
        --project="$PROJECT" \
        --database-version=POSTGRES_15 \
        --tier=db-f1-micro \
        --region="$REGION" \
        --root-password="$DB_PASS" \
        --storage-auto-increase \
        --quiet
    ok "created $CLOUDSQL_INSTANCE"
fi
wait_instance_runnable
ok "instance is RUNNABLE"
echo

# ---------------------------------------------------------------------------
bold "Step 2 — Database"
if gcloud sql databases describe "$DB_NAME" \
    --instance="$CLOUDSQL_INSTANCE" \
    --project="$PROJECT" >/dev/null 2>&1; then
    skip "database $DB_NAME already exists"
else
    gcloud sql databases create "$DB_NAME" \
        --instance="$CLOUDSQL_INSTANCE" \
        --project="$PROJECT" \
        --quiet
    ok "created database $DB_NAME"
fi
echo

# ---------------------------------------------------------------------------
bold "Step 3 — Schema init (pgvector + tables)"

PUBLIC_IP="$(gcloud sql instances describe "$CLOUDSQL_INSTANCE" \
    --project="$PROJECT" \
    --format='value(ipAddresses[0].ipAddress)' 2>/dev/null || true)"
if [[ -z "$PUBLIC_IP" ]]; then
    err "No public IP on $CLOUDSQL_INSTANCE — enable a PRIMARY IP to run init SQL from this machine."
    exit 1
fi

MY_IP="$(curl -4 -fsS ifconfig.me)"
AUTH_ADDED=0

cleanup_authorized_ip() {
    if [[ "$AUTH_ADDED" -eq 1 ]]; then
        local op
        op="$(gcloud sql instances patch "$CLOUDSQL_INSTANCE" \
            --project="$PROJECT" \
            --clear-authorized-networks \
            --quiet \
            --format='value(name)' 2>/dev/null || true)"
        wait_operation "$op"
        AUTH_ADDED=0
        ok "removed temporary authorized network $MY_IP/32"
    fi
}
trap cleanup_authorized_ip EXIT

op="$(gcloud sql instances patch "$CLOUDSQL_INSTANCE" \
    --project="$PROJECT" \
    --authorized-networks="${MY_IP}/32" \
    --quiet \
    --format='value(name)')"
wait_operation "$op"
AUTH_ADDED=1
ok "authorized $MY_IP/32 for init"

run_init_sql() {
    if command -v psql >/dev/null 2>&1; then
        PGPASSWORD="$DB_PASS" psql \
            -h "$PUBLIC_IP" \
            -U "$DB_USER" \
            -d "$DB_NAME" \
            -v ON_ERROR_STOP=1 \
            -f "$INIT_SQL"
        return 0
    fi

    warn "psql not found — trying gcloud sql connect (needs cloud-sql-proxy)"
    if PGPASSWORD="$DB_PASS" gcloud sql connect "$CLOUDSQL_INSTANCE" \
        --user="$DB_USER" \
        --database="$DB_NAME" \
        --project="$PROJECT" \
        --quiet < "$INIT_SQL" 2>/tmp/gcloud_connect.err; then
        return 0
    fi

    warn "gcloud sql connect failed — using psycopg via uv"
    if ! command -v uv >/dev/null 2>&1; then
        err "uv not found and no psql/cloud-sql-proxy available."
        err "Install one of:"
        err "  sudo apt-get install -y postgresql-client     # quickest"
        err "  gcloud components install cloud-sql-proxy"
        return 1
    fi
    PG_HOST="$PUBLIC_IP" \
    PG_USER="$DB_USER" \
    PG_PASS="$DB_PASS" \
    PG_DB="$DB_NAME" \
    SQL_PATH="$INIT_SQL" \
    uv run --project "$SCRIPT_DIR/.." python - <<'PY'
import os, sys
try:
    import psycopg
except ImportError:
    print("psycopg not installed in this project env", file=sys.stderr)
    sys.exit(1)

sql = open(os.environ["SQL_PATH"], "r").read()
dsn = (
    f"host={os.environ['PG_HOST']} "
    f"user={os.environ['PG_USER']} "
    f"password={os.environ['PG_PASS']} "
    f"dbname={os.environ['PG_DB']} "
    f"sslmode=require"
)
with psycopg.connect(dsn, autocommit=True) as conn:
    with conn.cursor() as cur:
        cur.execute(sql)
print("schema applied via psycopg")
PY
}

run_init_sql
ok "applied $INIT_SQL"
cleanup_authorized_ip
trap - EXIT
echo

# ---------------------------------------------------------------------------
bold "Connection details"
SOCKET_DSN="postgresql://${DB_USER}:${DB_PASS}@/${DB_NAME}?host=/cloudsql/${CONNECTION_NAME}"
DIRECT_DSN="postgresql://${DB_USER}:${DB_PASS}@${PUBLIC_IP}:5432/${DB_NAME}"

echo
echo "Instance connection name (for --add-cloudsql-instances):"
echo "  $CONNECTION_NAME"
echo
echo "POSTGRES_DSN for .env (Cloud Run / Cloud SQL socket):"
echo "  $SOCKET_DSN"
echo
echo "Direct-connect DSN (local debugging via public IP — authorize your IP first):"
echo "  $DIRECT_DSN"
echo
warn "Save DB_PASS now if you did not set it via env — it was reset on this run."
echo "  DB_PASS=$DB_PASS"
echo
bold "Done."
