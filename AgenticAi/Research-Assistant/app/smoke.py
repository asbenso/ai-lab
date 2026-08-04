"""Day-0 smoke test.

Verifies that this machine can:
- Reach AWS Bedrock and call gpt-oss-120b (OpenAI's open-weight model hosted on Bedrock).
- Reach GCP Vertex AI and call Gemini.
- Connect to the local pgvector Postgres (port 5433).

Run with: `uv run python -m app.smoke`
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from rich.console import Console

console = Console()


BEDROCK_MODEL = "bedrock_converse:openai.gpt-oss-120b-1:0"
VERTEX_MODEL = "google_vertexai:gemini-2.5-pro"
DEFAULT_POSTGRES_DSN = "postgresql://postgres:postgres@localhost:5433/monk"


def _disable_langsmith() -> None:
    """LangSmith tracing has nothing to add to a smoke test and a bad/missing key
    floods stderr with 403s that hide the real errors. Off for this script."""
    from app.tracing import disable_langsmith_tracing

    disable_langsmith_tracing()


def check_bedrock() -> bool:
    console.print("[bold]1/3 AWS Bedrock (gpt-oss-120b)[/]")
    try:
        from langchain.chat_models import init_chat_model

        # gpt-oss-120b is a reasoning model. Give it enough output budget for
        # internal thinking plus the visible reply, and request low reasoning
        # effort so the smoke test stays snappy.
        model = init_chat_model(
            BEDROCK_MODEL,
            region_name=os.getenv("AWS_REGION", "us-east-1"),
            max_tokens=512,
        )
        resp = model.invoke("Reply with exactly: Hello from gpt-oss on Bedrock!")
        text = (resp.content if isinstance(resp.content, str) else str(resp.content)).strip()
        if not text:
            console.print("  [red]ERR[/] Bedrock returned an empty response.")
            return False
        console.print(f"  [green]ok[/]  -> {text!r}")
        return True
    except Exception as e:
        msg = str(e)
        console.print(f"  [red]ERR[/] {type(e).__name__}: {msg}")
        if "use case details" in msg.lower():
            # Anthropic-specific form. gpt-oss on Bedrock should not trigger this,
            # but if the wrong model ID slipped in, point the way out.
            console.print(
                "  hint: this error is Anthropic-specific. Confirm MONK_MODEL is "
                "[cyan]bedrock_converse:openai.gpt-oss-120b-1:0[/], not a Claude ID."
            )
        elif "AccessDenied" in type(e).__name__ or "AccessDenied" in msg or "not authorized" in msg.lower():
            console.print(
                "  hint: your Bedrock model-access request for gpt-oss-120b is pending or missing. "
                "Open [cyan]https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess[/] "
                "and request access to [yellow]OpenAI - gpt-oss-120b[/]. Usually granted in under 5 minutes."
            )
        elif "ResourceNotFound" in type(e).__name__ or "does not exist" in msg.lower():
            console.print(
                "  hint: gpt-oss-120b may not be available in your region. "
                "Try [yellow]AWS_REGION=us-west-2[/] in your .env, or fall back to "
                "[yellow]MONK_MODEL=bedrock_converse:openai.gpt-oss-20b-1:0[/]."
            )
        return False


def check_vertex() -> bool:
    console.print("\n[bold]2/3 GCP Vertex AI (Gemini)[/]")
    try:
        from langchain.chat_models import init_chat_model

        # Gemini 2.5 Pro is a thinking model - small token budgets get eaten by
        # internal reasoning and the user-visible reply comes back empty. 256 is
        # plenty for "Hello from Gemini on Vertex!" plus the thinking overhead.
        model = init_chat_model(
            VERTEX_MODEL,
            project=os.environ.get("GCP_PROJECT"),
            location=os.environ.get("GCP_LOCATION", "us-central1"),
            max_output_tokens=256,
        )
        resp = model.invoke("Reply with exactly: Hello from Gemini on Vertex!")
        text = (resp.content if isinstance(resp.content, str) else str(resp.content)).strip()
        if not text:
            console.print(
                "  [red]ERR[/] Vertex returned an empty response. "
                "Likely a reasoning-model token-budget issue - bump max_output_tokens."
            )
            return False
        console.print(f"  [green]ok[/]  -> {text!r}")
        return True
    except Exception as e:
        console.print(f"  [red]ERR[/] {type(e).__name__}: {e}")
        return False


def check_postgres() -> bool:
    console.print("\n[bold]3/3 Postgres + pgvector[/]")
    dsn = os.getenv("POSTGRES_DSN", DEFAULT_POSTGRES_DSN)
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=5) as conn, conn.cursor() as cur:
            cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
            row = cur.fetchone()
        if row is None:
            console.print(
                "  [red]ERR[/] connected, but pgvector extension is missing. "
                "You're probably hitting a host Postgres instead of the Docker container."
            )
            console.print("  hint: confirm POSTGRES_DSN points at port 5433 and run [yellow]docker compose up -d postgres[/]")
            return False
        console.print(f"  [green]ok[/]  -> pgvector {row[0]}")
        return True
    except Exception as e:
        msg = str(e)
        console.print(f"  [red]ERR[/] {type(e).__name__}: {msg}")
        if 'role "postgres" does not exist' in msg or "password authentication failed" in msg:
            console.print(
                "  hint: you have a [yellow]host Postgres[/] already running on this port. "
                "The project Postgres now listens on [yellow]5433[/] to avoid that clash. "
                "Reset POSTGRES_DSN in your .env to "
                "[cyan]postgresql://postgres:postgres@localhost:5433/monk[/], then "
                "[yellow]docker compose up -d postgres[/]."
            )
        else:
            console.print("  hint: run [yellow]docker compose up -d postgres[/] and confirm port 5433 is free")
        return False


def main() -> int:
    load_dotenv()
    _disable_langsmith()
    console.rule("[bold orange1]Monk Technologies - smoke test[/]")
    results = [check_bedrock(), check_vertex(), check_postgres()]
    console.print()
    if all(results):
        console.print("[bold green]All systems go. See you in class.[/]")
        return 0
    console.print("[bold red]Some checks failed. See PREWORK.md troubleshooting.[/]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
