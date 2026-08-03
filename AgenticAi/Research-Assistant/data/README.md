# Sample data

This folder ships with three sample document corpora (for Project 1) and three sample ticket datasets (for Project 2). On Day 2 we'll ingest one corpus into pgvector; on Day 5 we'll load one ticket dataset.

## Project 1 corpora

- `sample-corpus/aws-docs/` - a curated subset of public AWS documentation (IAM, S3, Lambda, Bedrock). About 200 chunks after ingestion.
- `sample-corpus/k8s-docs/` - a curated subset of Kubernetes documentation. About 250 chunks.
- `sample-corpus/anthropic-policy/` - publicly available Anthropic usage policy + privacy docs. About 50 chunks.

Each corpus is a flat directory of `.md` files. Each file's first line is the source URL as a comment, e.g.

```
<!-- source: https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys_manage.html -->

# Managing access keys for IAM users
...
```

The ingestion script reads the source URL from this comment.

## Project 2 datasets

- `support/` - 200 fake customer-support tickets + a runbook corpus + a taxonomy.
- `it-helpdesk/` - 200 fake IT helpdesk tickets + runbooks + taxonomy.
- `oncall/` - 200 fake on-call alert payloads + runbooks + taxonomy.

Each directory contains:

```
{domain}/
├── tickets.jsonl            # one ticket per line
├── runbooks/                # markdown files with source urls in first line comment
├── taxonomy.yaml            # categories + severities
├── mock_logs.json           # mock CloudWatch logs keyed by service
├── mock_metrics.json        # mock metric snapshots
└── historical_tickets.jsonl # past tickets for `get_ticket_history` tool
```

## How the corpora were built

Each corpus is hand-curated, public-domain, and small enough to embed in under a minute. Total embedding cost across all corpora is ~$0.10 on Bedrock Titan Embeddings V2. We do NOT include scraped or copyrighted content.

> **Note**: this scaffold ships with the directory structure and a few example files. The full corpora are downloaded by `scripts/fetch_data.sh` (run during pre-work) to keep the repo lightweight.
