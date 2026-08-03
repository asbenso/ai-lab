"""Quick CLI: vector search a table. Used to sanity-check ingestion.

    uv run python -m ingest.search "iam key rotation" --table docs
"""
from __future__ import annotations

import argparse
import json
import sys

from app.tools.search_local_docs import search_local_docs


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("query")
    p.add_argument("--table", default="docs")
    p.add_argument("--k", type=int, default=5)
    args = p.parse_args()
    rows = search_local_docs.invoke({"query": args.query, "k": args.k, "table": args.table})
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
