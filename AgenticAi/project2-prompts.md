# Project 2 - Autonomous Ticket Triage Agent - Cursor prompt library

Every Cursor Composer prompt for Project 2, in the order they're issued in class.

> **Session mapping**: Session 7 = Day 5 (memory + P2 skeleton). Session 8 = Day 6 H1 (Triager). Session 9 = Day 6 H2-H4 (Investigator, Responder, HITL). Session 10 = Day 7 (deploys). Session 11 = Day 8 H1-H2 (evals, security). Session 12 = Day 8 H3 (billing + demo). Prompt IDs like `Day 6 H1` are stable references.

---

## Day 5 H2 - Memory upgrade on Project 1 (Session 7)

(This prompt is technically for Project 1's repo, but it's where we teach memory.)

> In the Project 1 repo, create `app/memory.py`:
>
> 1. Wrap a memory store: use `langgraph.store.memory.InMemoryStore` when `MONK_MEMORY=memory`, `langgraph.store.postgres.PostgresStore` when `MONK_MEMORY=postgres`.
> 2. Export `recall(store, namespace, query, k=3) -> list[dict]` - searches for memories. Each item has `key`, `value` (a dict), `score`.
> 3. Export `remember(store, namespace, content: str, kind: Literal["preference", "fact"])` - writes a memory; auto-generates a key.
> 4. Add a new `recall_node` to the graph that runs after START: it pulls top-3 memories for the current user and injects them into the planner prompt as `Memories: ...`.
> 5. Add a new `extract_node` after the writer: it asks the LLM "Looking at the user's question and the report, is there any preference or stable fact about this user worth remembering? Return JSON with `worth_remembering: bool` and `content: str`." If yes, call `remember(...)`.
> 6. Wire: `START -> recall -> planner -> researcher -> writer -> guard -> extract -> END`.

---

## Day 5 H4 - Project 2 skeleton (Session 7)

> Initialize a new project `monk-ticket-triage`. Create the following structure with stub implementations:
>
> 1. `app/state.py` defining `class TicketState(TypedDict)` with fields:
>    - `ticket_id: str`
>    - `raw: dict` (the incoming ticket: subject, body, sender, attachments)
>    - `domain: Literal["support", "it-helpdesk", "oncall"]`
>    - `classification: dict | None` (will be filled by Triager)
>    - `severity: Literal["P1", "P2", "P3", "P4"] | None`
>    - `findings: list[dict]`
>    - `draft: dict | None`
>    - `approval: Literal["pending", "approved", "edited", "rejected"]`
>    - `sent: bool`
>    - `step_log: list[str]`
>
> 2. `app/agents/supervisor.py` with `supervisor_node(state) -> dict`. Returns `{"next": "triager"|"investigator"|"responder"|"hitl"|"END"}` based on rules:
>    - If `classification is None`: "triager".
>    - Else if `findings == []`: "investigator".
>    - Else if `draft is None`: "responder".
>    - Else if `approval == "pending"`: "hitl".
>    - Else if `approval in ("approved", "edited")` and not `sent`: "send".
>    - Else "END".
>
> 3. Stub `app/agents/triager.py`, `app/agents/investigator.py`, `app/agents/responder.py` each as a function that appends a step_log line and returns.
>
> 4. `app/graph.py` that wires `START -> supervisor` and from supervisor uses `add_conditional_edges` to route to the named node. Each worker returns to supervisor. Use a `SqliteSaver` for now.
>
> Add a small `__main__` test that feeds a sample ticket dict and prints each routing step.

---

## Day 6 H1 - Real Triager (Session 8)

> Replace the stub in `app/agents/triager.py`:
>
> 1. Load taxonomy from `data/{state['domain']}/taxonomy.yaml`. The file has `categories: [{name, description}]` and `severities: [P1, P2, P3, P4]`.
> 2. Build a Pydantic `TriageOutput(BaseModel)` with `category: str`, `severity: Literal["P1","P2","P3","P4"]`, `confidence: float`, `rationale: str`.
> 3. Use `init_chat_model(...).with_structured_output(TriageOutput)`.
> 4. Prompt: "You are a {domain} triage analyst. Available categories: {taxonomy}. Given this ticket: {ticket}, choose the best category and severity. Provide a brief rationale. Be conservative on severity."
> 5. Leave a placeholder comment `# TODO: episodic memory examples` near the prompt - we'll fill it on Day 6 H3.
> 6. Return `{"classification": {"category": out.category, "confidence": out.confidence, "rationale": out.rationale}, "severity": out.severity, "step_log": [...]}`.
>
> Validate that `out.category` is in the loaded taxonomy; if not, default to `"unknown"` and force severity to `P3`.

---

## Day 6 H2 - The Investigator and its tools (Session 9)

**First the tools**:

> Create four tool files under `app/tools/`:
>
> 1. `query_logs.py` - `query_logs(service: str, since: str = "1h") -> list[dict]`. Reads `data/{state['domain']}/mock_logs.json` keyed by service. Filters by approximate "since" (parse "1h", "30m", etc.). Each entry is `{"timestamp", "level", "message"}`. Wrap with `@tool`.
>
> 2. `query_metrics.py` - `query_metrics(service: str, metric: str, since: str = "1h") -> dict`. Reads `data/{domain}/mock_metrics.json`. Returns `{"service", "metric", "current", "avg", "p95", "trend"}`.
>
> 3. `search_runbooks.py` - imports `search_local_docs` from a shared utility module and calls it with `table="runbooks_" + domain.replace("-", "_")` (Postgres identifiers cannot contain `-`, so `it-helpdesk` becomes `it_helpdesk`). Re-exports as `search_runbooks(query: str, k: int = 3)`.
>
> 4. `get_ticket_history.py` - `get_ticket_history(user_id: str, k: int = 5) -> list[dict]`. Reads `data/{domain}/historical_tickets.jsonl`, filters by user, returns the last k.

**Then the Investigator agent**:

> Replace the stub in `app/agents/investigator.py`:
>
> 1. Import the four tools and bind them to `init_chat_model`.
> 2. Build a system prompt: "You are an investigator. Given a classified ticket, gather enough context to write an informed response. Use tools to fetch logs, metrics, runbooks, and the user's ticket history. Stop calling tools when you can clearly explain what happened and what should be done. Budget: 8 tool calls max."
> 3. Loop with a max of 8 tool calls.
> 4. After the loop, ask the LLM (no tools) to summarise findings as a JSON list of `{"claim": str, "source": str, "tool": str}`.
> 5. Return `{"findings": [...], "step_log": [...]}`.
> 6. Important: log every tool call to step_log with truncated args.

---

## Day 6 H3 - The Responder and the memory layers (Session 9)

**Memory first**:

> Create three files in `app/memory/`:
>
> 1. `semantic.py` - wraps a `LangGraphStore` with `recall_user(user_id, k)` and `remember_user(user_id, content)` for per-user facts.
>
> 2. `episodic.py` - export `similar_past_cases(ticket_text, domain, k=3) -> list[dict]`. Backed by pgvector over a `past_resolutions` table. Each row has `ticket_text`, `resolution_text`, embedding.
>
> 3. `procedural.py` - export `get_responder_prompt(domain, version="latest") -> str` and `set_responder_prompt(domain, prompt: str)`. Storage is a JSON file `data/prompts/responder_{domain}.json` with a version history. Default prompts ship in the repo.

**Then the Responder**:

> Replace the stub in `app/agents/responder.py`:
>
> 1. Load the procedural memory (style prompt) via `get_responder_prompt(state["domain"])`.
> 2. Pull 3 episodic examples via `similar_past_cases(state["raw"]["body"], state["domain"], k=3)`.
> 3. Pull user-specific semantic memories via `recall_user(state["raw"]["sender"], k=3)`.
> 4. Build the prompt: include the style prompt as the system message, include the 3 episodic examples as few-shot pairs, include semantic memories as a "What we know about this user:" section, then the actual ticket + classification + findings.
> 5. Use `with_structured_output(ResponderOutput)` where `ResponderOutput` is `{subject: str, body: str, recommended_action: Literal["send", "escalate"], confidence: float, risk_flags: list[str]}`.
> 6. Post-process: if `confidence < 0.6`, or if the body mentions "refund" / "credit" / "guarantee" / "tomorrow" / "by EOD", or if any obvious PII pattern (email, phone) appears in the body, force `recommended_action="escalate"` and add the trigger to `risk_flags`.
> 7. Return `{"draft": out.model_dump(), "approval": "pending", "step_log": [...]}`.

---

## Day 6 H4 - Human-in-the-loop (Session 9)

> Create `app/hitl.py`:
>
> 1. Export `hitl_node(state: TicketState) -> dict`. Inside it, call `interrupt({"draft": state["draft"], "classification": state["classification"], "severity": state["severity"], "findings": state["findings"], "raw": state["raw"]})`. The return value of `interrupt(...)` is the resume payload; expect it to be `{"action": "approve"|"edit"|"reject", "edited_body": str | None}`.
> 2. Apply the decision: if `approve`, set `approval="approved"`. If `edit`, set `approval="edited"` and update `draft["body"] = payload["edited_body"]`. If `reject`, set `approval="rejected"`.
> 3. Return the updated state with a step_log entry.
>
> Also create `app/agents/send.py` with `send_node(state) -> dict`:
> 1. Only runs if `approval in ("approved", "edited")`.
> 2. Calls the `send_response` tool from `app/tools/send_response.py` (a mock - logs to a file and returns a fake ticket-id).
> 3. Returns `{"sent": True, "step_log": [...]}`.
>
> Update `app/graph.py` to route `supervisor -> hitl` when approval is pending, and `supervisor -> send` after approval.

**Then the approval API**:

> In `app/main.py` add:
>
> 1. `POST /ingest` with `{ticket: dict, domain: str}` - creates a `thread_id`, kicks off the graph in a background task.
> 2. `GET /pending` returns a list of paused thread_ids and the payload from each pending HITL interrupt.
> 3. `POST /approve/{thread_id}` with `{action: "approve"|"edit"|"reject", edited_body?: str}`. Calls `graph.invoke(Command(resume=payload), config={"configurable": {"thread_id": thread_id}})` to resume.
>
> Also create `app/ui/approval.html` - HTMX page that:
> - Polls `/pending` every 5 seconds and renders pending drafts as cards.
> - Each card shows: subject, classification + severity, findings as bullets, the draft body in an editable `<textarea>`, and three buttons (Approve, Save & Approve as Edit, Reject).
> - On button click, POSTs to `/approve/{thread_id}` and removes the card on success.

---

## Day 7 H2 - AgentCore deploy (Session 10)

> Create `deploy/agentcore_entrypoint.py`:
>
> ```python
> import os
> from bedrock_agentcore import BedrockAgentCoreApp
> from langgraph.checkpoint.postgres import PostgresSaver
> from langgraph.store.postgres import PostgresStore
> from app.graph import build_graph_with_backends
>
> app = BedrockAgentCoreApp()
>
> @app.entrypoint
> async def handler(payload, context):
>     graph = build_graph_with_backends(
>         saver=PostgresSaver.from_conn_string(os.environ["POSTGRES_DSN"]),
>         store=PostgresStore.from_conn_string(os.environ["POSTGRES_DSN"]),
>     )
>     config = {"configurable": {"thread_id": context.session_id}}
>     async for event in graph.astream_events(payload, config=config, version="v2"):
>         await app.streaming.write(event)
> ```
>
> Also create `deploy/deploy_agentcore.sh`:
>
> ```bash
> #!/usr/bin/env bash
> set -euo pipefail
> agentcore configure \
>     --name monk-ticket-triage \
>     --entrypoint deploy/agentcore_entrypoint.py \
>     --runtime python3.11 \
>     --memory 1024 \
>     --timeout 600
> agentcore launch
> echo "Done. agentcore logs monk-ticket-triage --follow"
> ```

And refactor `app/graph.py` to export `build_graph_with_backends(saver, store)` in addition to the dev-mode `build_graph()`.

---

## Day 7 H4 - Vertex Agent Engine deploy (Session 10)

> Create `deploy/vertex_engine_deploy.py`:
>
> ```python
> import os
> import vertexai
> from vertexai import agent_engines
> from app.graph import build_graph
>
> vertexai.init(
>     project=os.environ["GCP_PROJECT"],
>     location=os.environ.get("GCP_LOCATION", "us-central1"),
>     staging_bucket=f"gs://{os.environ['GCP_BUCKET']}",
> )
>
> langgraph_agent = agent_engines.LanggraphAgent(
>     model="gemini-2.5-pro",
>     runnable=build_graph(),
>     enable_tracing=True,
> )
>
> deployed = agent_engines.create(
>     langgraph_agent,
>     requirements=[
>         "langgraph>=1.2,<2",
>         "langchain-google-vertexai",
>         "psycopg[binary]",
>         "pydantic>=2",
>         "pyyaml",
>     ],
>     display_name="monk-ticket-triage",
> )
> print("Deployed:", deployed.resource_name)
> ```
>
> Also create `deploy/deploy_vertex_engine.sh` that runs the above and saves the resource name to `.env.deployed`.

---

## Day 8 H1 - Eval suite (Session 11)

> Create four eval scripts under `evals/`:
>
> 1. `triager_eval.py` - per-row run the Triager alone, compute category exact-match and severity exact-match. Print confusion matrix.
>
> 2. `investigator_eval.py` - given pre-classified tickets (a separate dataset under `evals/investigator_golden.jsonl` with `ticket`, `classification`, `expected_finding_keywords`), run the Investigator alone. Score: does each finding's claim contain at least one expected keyword? LLM-as-judge for "are these findings sufficient and grounded?".
>
> 3. `responder_eval.py` - given pre-investigated tickets, run the Responder. Score: (a) escalation precision/recall against ground-truth, (b) LLM-as-judge quality 1-5.
>
> 4. `e2e_eval.py` - full pipeline run on the golden dataset. Pass = correct category + reasonable response + correct escalation decision (against ground-truth labels).
>
> Each script uploads to LangSmith as an experiment with a clear name. Each prints a final pass-rate.

---

## Day 8 H2 - Security injection eval (Session 11)

> Create `security/attacks.jsonl` with 20 attack payloads as ticket bodies, each labelled `name` and `expected_outcome` (either `blocked` or `escalated`).
>
> Create `security/injection_eval.py`:
>
> 1. For each attack, feed it through the full pipeline.
> 2. Verify outcome: `blocked` means the guardrail returned a refusal OR the structured output failed to materialise. `escalated` means the Responder set `recommended_action="escalate"` and the HITL path triggered.
> 3. Print per-attack pass-fail with the actual observed outcome.

---

## Day 8 H3 - Billing alerts (Session 12)

> Create `scripts/setup_billing_alerts.sh`:
>
> ```bash
> #!/usr/bin/env bash
> set -euo pipefail
> EMAIL="${ALERT_EMAIL:?set ALERT_EMAIL}"
>
> # AWS budget alert at $10/day
> aws budgets create-budget --account-id "$(aws sts get-caller-identity --query Account --output text)" \
>     --budget '{"BudgetName":"monk-bootcamp-daily","BudgetLimit":{"Amount":"10","Unit":"USD"},"TimeUnit":"DAILY","BudgetType":"COST"}' \
>     --notifications-with-subscribers '[{"Notification":{"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN","Threshold":100},"Subscribers":[{"SubscriptionType":"EMAIL","Address":"'"$EMAIL"'"}]}]'
>
> # GCP budget alert at $10/day
> BILLING_ACCOUNT="$(gcloud billing accounts list --format='value(name)' --limit=1)"
> gcloud billing budgets create \
>     --billing-account="$BILLING_ACCOUNT" \
>     --display-name="monk-bootcamp-daily" \
>     --budget-amount="10USD" \
>     --threshold-rule=percent=1.0,basis=current-spend \
>     --calendar-period=daily
> echo "Alerts set up. Watch $EMAIL."
> ```

---

## Bonus stretch prompts

**Auto-prompt-tuning**:

> Add `app/cron/refine_responder_prompt.py`: a script that pulls the last 50 HITL outcomes from a log, asks an LLM to summarise common edits the humans made, and proposes a v+1 of the procedural-memory prompt. Outputs to stdout; instructor approves manually.

**Slack notifier**:

> Add `app/tools/notify_slack.py` exporting `notify_slack(channel: str, blocks: list[dict])`. Wire it into the `send_node`: after a P1 incident is approved, also post to `#incidents`.

**Bedrock KB swap for runbooks**:

> Replace the body of `search_runbooks` to call AWS Bedrock Knowledge Bases instead of pgvector. Keep the function signature identical.

**Ops dashboard**:

> Create `app/ops/dashboard.py` - a Streamlit app showing: today's classifications by category (bar chart), severity distribution, escalation rate, average HITL latency, last 20 resolved tickets with status badges.
