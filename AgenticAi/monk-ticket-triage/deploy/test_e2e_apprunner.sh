#!/usr/bin/env bash
# End-to-end smoke test: ingest ticket -> wait for HITL -> approve -> verify sent.
set -euo pipefail

BASE_URL="${1:-}"
if [[ -z "$BASE_URL" ]]; then
    echo "Usage: $0 https://your-service.us-east-1.awsapprunner.com"
    exit 1
fi
BASE_URL="${BASE_URL%/}"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$*" >&2; }

PAYLOAD='{
  "ticket": {
    "subject": "Cannot log in to VPN",
    "body": "VPN client hangs on connecting since this morning.",
    "sender": "alex@example.com",
    "attachments": []
  },
  "domain": "it-helpdesk"
}'

bold "E2E test against $BASE_URL"

bold "1. Health"
curl -fsS "$BASE_URL/health" | grep -q '"ok"' && ok "/health"

bold "2. Ingest ticket"
INGEST="$(curl -fsS -X POST "$BASE_URL/ingest" -H 'Content-Type: application/json' -d "$PAYLOAD")"
THREAD_ID="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['thread_id'])" "$INGEST")"
TICKET_ID="$(python3 -c "import json,sys; print(json.loads(sys.argv[1])['ticket_id'])" "$INGEST")"
ok "thread_id=$THREAD_ID ticket_id=$TICKET_ID"

bold "3. Wait for pending draft (up to 3 min)"
FOUND=0
for i in $(seq 1 36); do
    PENDING="$(curl -fsS "$BASE_URL/pending")"
    if echo "$PENDING" | python3 -c "import json,sys; items=json.load(sys.stdin); tid=sys.argv[1]; sys.exit(0 if any(x['thread_id']==tid for x in items) else 1)" "$THREAD_ID" 2>/dev/null; then
        FOUND=1
        ok "Draft visible in /pending after ~$((i*5))s"
        break
    fi
    sleep 5
done
if [[ "$FOUND" -ne 1 ]]; then
    err "Timed out waiting for /pending to show thread $THREAD_ID"
    echo "Last /pending response: $PENDING"
    exit 1
fi

bold "4. Approve draft"
APPROVE="$(curl -fsS -X POST "$BASE_URL/approve/$THREAD_ID" \
    -H 'Content-Type: application/json' \
    -d '{"action":"approve"}')"
echo "$APPROVE" | python3 -c "import json,sys; r=json.load(sys.stdin); assert r.get('approval') in ('approved','edited'), r; assert r.get('sent') is True, r; print('approval=', r['approval'], 'sent=', r['sent'])"
ok "Approved and sent"

bold "E2E passed."
