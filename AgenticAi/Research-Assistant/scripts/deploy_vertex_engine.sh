#!/usr/bin/env bash
# Monk Technologies - deploy Project 2 (Ticket Triage) to GCP Vertex AI Agent Engine.
# Day 7. Calls deploy/vertex_engine_deploy.py.

set -euo pipefail

bold() { printf "\033[1m%s\033[0m\n" "$*"; }

if [[ -f .env ]]; then
    # shellcheck disable=SC2046
    export $(grep -v '^#' .env | xargs -0 2>/dev/null || true)
fi

bold "Monk Technologies - deploy to Vertex AI Agent Engine"
echo "  project=${GCP_PROJECT:?set GCP_PROJECT}"
echo "  location=${GCP_LOCATION:-us-central1}"
echo "  bucket=${GCP_BUCKET:?set GCP_BUCKET}"
echo

uv run python deploy/vertex_engine_deploy.py | tee .env.deployed

bold "Done."
echo "Resource name saved to .env.deployed"
