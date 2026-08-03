# Project 1 - AI Research Assistant - Cursor prompt library

Every Cursor Composer prompt for Project 1, in the order they're issued in class.

> **Convention used here**: each prompt is in a fenced blockquote. Paste verbatim into Cursor Composer (Cmd-I). When something is parameterised (`{like_this}`), substitute before sending.

> **Session mapping**: Session 3 = LangGraph concepts (Day 3 H1, H2a). Session 4 = build nodes + UI (Day 3 H2b-H2d, H3, H4). Session 5 = guardrails + golden set (Day 4 H1c, H1b, H1, H2a — issued in that order). Session 6 = eval suite + deploy (Day 4 H2b-H2d, H4). Prompt IDs like `Day 3 H2c` are stable references.

---

## Day 3 H1 - Tiny graph demo (Session 3)

> In `app/playground/tiny_graph.py`, write a 15-line LangGraph demo:
>
> 1. Define a `TypedDict S` with fields `q: str` and `a: str`.
> 2. One node `respond(state: S) -> dict` that returns `{"a": f"You asked: {state['q']}"}`.
> 3. Wire `START -> respond -> END` and compile.
> 4. In `__main__`, call `app.invoke({"q": "hello"})` and print.
>
> Use the `langgraph` import paths pinned in `pyproject.toml` (currently 0.2.x): `from langgraph.graph import END, START, StateGraph`. Show the LangSmith trace URL after the invoke.

---

## Day 3 H2a - ResearchState + build_graph stub (Session 3)

> Create `app/graph.py`:
>
> 1. Import `TypedDict` from `typing` (use the standard `typing.TypedDict`).
> 2. Define `class ResearchState(TypedDict)` with these fields:
>   - `question: str` - the user's question.
>   - `sub_questions: list[dict]` - each `{"text": str, "source": Literal["web", "local", "both"]}`.
>   - `findings: list[dict]` - each `{"sub_question_index": int, "claim": str, "evidence_url": str, "evidence_text": str}`.
>   - `report: str` - final markdown report.
>   - `step_log: list[str]` - human-readable trace for the UI.
> 3. Export `build_graph()` that:
>   - Wires `START -> planner -> researcher -> writer -> END`.
>   - Uses `SqliteSaver.from_conn_string("checkpoints.sqlite")` as the checkpointer.
>   - Compiles with `.compile(checkpointer=saver)`.
> 4. For now, import `planner_node`, `researcher_node`, `writer_node` from `app.nodes.{planner,researcher,writer}` (we'll write those next; leave them as `pass` stubs in those files if not yet created).

---

## Day 3 H2b - Planner node (Session 4)

> Create `app/nodes/planner.py` exporting `planner_node(state: ResearchState) -> dict`.
>
> 1. Define a Pydantic v2 model `SubQuestion(BaseModel)` with `text: str` and `source: Literal["web", "local", "both"]`.
> 2. Define `PlannerOutput(BaseModel)` with `sub_questions: list[SubQuestion]`.
> 3. Build a system prompt: "You are a research planner. Decompose the user's question into 3-7 sub-questions that, taken together, fully cover the question. Tag each as 'web' (current/news/general), 'local' (likely in our internal docs corpus), or 'both'. Output strict JSON."
> 4. Use `init_chat_model(os.getenv('MONK_MODEL', '...')).with_structured_output(PlannerOutput)`.
> 5. Return `{"sub_questions": [sq.model_dump() for sq in result.sub_questions], "step_log": state["step_log"] + [f"Planner: {len(result.sub_questions)} sub-questions"]}`.

---

## Day 3 H2c - Researcher node (Session 4)

> Create `app/nodes/researcher.py` exporting `researcher_node(state: ResearchState) -> dict`.
>
> 1. Import the four tools: `web_search`, `fetch_url`, `search_local_docs`, `summarize` from `app.tools.`*.
> 2. Bind them to `init_chat_model(...)`.
> 3. For each sub-question in `state["sub_questions"]`, run a small loop (max 4 tool calls per sub-question):
>   - Build messages = [SystemMessage("You are a focused researcher. Use tools to find 1-3 supporting facts with real source URLs for the given sub-question. When you have enough, reply with a JSON list of findings."), HumanMessage(sub_q.text)].
>   - Loop: invoke model, if `tool_calls`, run them and append `ToolMessage`s; otherwise parse the JSON list of findings.
> 4. Each finding is `{"sub_question_index": int, "claim": str, "evidence_url": str, "evidence_text": str}`.
> 5. Validate `evidence_url` actually appeared somewhere in the tool messages (anti-hallucination check). Drop the finding if not.
> 6. Append a `step_log` entry per tool call: e.g. `"[sub 2/5] web_search('...')"`.
> 7. Return `{"findings": all_findings, "step_log": [...]}`.

---

## Day 3 H2d - Writer node (Session 4)

> Create `app/nodes/writer.py` exporting `writer_node(state: ResearchState) -> dict`.
>
> 1. Build a prompt:
>   - System: "You are writing a research report. Produce a markdown report with: 1) a 2-3 sentence executive summary, 2) one H2 section per sub-question, 3) inline `[n]` citations after each factual claim, 4) a numbered Sources section at the end listing each unique URL once. Never invent a URL or fact - only use the supplied findings."
>   - Human: a JSON blob of `{"question": ..., "sub_questions": ..., "findings": ...}`.
> 2. Call the LLM (no tools). Return `{"report": ai_msg.content, "step_log": state["step_log"] + ["Writer: report drafted"]}`.
> 3. After the LLM returns, post-process: build a set of allowed URLs from `state["findings"]`. Scan the report for markdown URLs `[text](url)` and the Sources section. If any URL isn't in the allowed set, append a warning line: `"> WARNING: filtered hallucinated citations: {bad_urls}"`.

---

## Day 3 H3 - Streaming helper (Session 4)

> In `app/graph.py`, add an async helper:
>
> ```python
> async def stream_research(question: str, thread_id: str):
>     graph = build_graph()
>     async for event in graph.astream_events(
>         {"question": question, "sub_questions": [], "findings": [], "report": "", "step_log": []},
>         config={"configurable": {"thread_id": thread_id}},
>         version="v2",
>     ):
>         yield event
> ```
>
> Make sure `build_graph()` is cached at module level so a second call doesn't rebuild it.

---

## Day 3 H4 - FastAPI + HTMX UI (Session 4)

> Create three files:
>
> 1. `app/main.py` - FastAPI app with:
>   - `GET /` returns `app/ui/index.html`.
>   - `POST /research` accepts `{"question": str}`, creates a thread_id (uuid4), starts the graph in a background task, returns `{"thread_id": ...}`.
>   - `GET /stream/{thread_id}` is a Server-Sent Events endpoint that yields each event from `stream_research(...)` as `data: {json}\n\n`.
>   - Serve static files from `app/ui/` at `/static`.
> 2. `app/ui/index.html` - a single-page HTMX UI:
>   - Header with the Monk Technologies logo (`/static/logo.png`) and the title "AI Research Assistant".
>   - A `<textarea>` for the question and a "Research" button.
>   - Two panels side-by-side: left "Progress" (live step_log), right "Report" (markdown rendered with the marked.js CDN).
>   - Use the HTMX SSE extension. On button click, POST `/research`, then connect to `/stream/{thread_id}` and append events.
> 3. `app/ui/styles.css` - clean styles, palette: orange `#FF8A47`, pink `#FF2E78`, text `#16161C` on white background. Inter font. Card layout with soft shadows.
>
> No build step. No npm. Just HTML + a `<script src="https://unpkg.com/htmx.org@1.9.10"></script>`.

---

## Day 4 H1c - Guardrail before/after demo (Session 5)

Prerequisite — create the standard `monk-research-guardrail` first (AWS console, or this CLI command; region `us-east-1`, needs `bedrock:CreateGuardrail`):

```bash
aws bedrock create-guardrail \
  --region us-east-1 \
  --name "monk-research-guardrail" \
  --description "Monk bootcamp standard guardrail for Project 1" \
  --blocked-input-messaging "Sorry — the Monk Research Assistant only handles business and technology research, not cooking questions." \
  --blocked-outputs-messaging "Sorry — the Monk Research Assistant only handles business and technology research, not cooking questions." \
  --topic-policy-config '{"topicsConfig":[{"name":"Cooking and Recipes","definition":"Any request for cooking recipes, ingredients, or step-by-step food preparation instructions.","examples":["give me a recipe for","how do I cook","ingredients for"],"type":"DENY"}]}' \
  --content-policy-config '{"filtersConfig":[{"type":"HATE","inputStrength":"HIGH","outputStrength":"HIGH"},{"type":"INSULTS","inputStrength":"HIGH","outputStrength":"HIGH"},{"type":"SEXUAL","inputStrength":"HIGH","outputStrength":"HIGH"},{"type":"VIOLENCE","inputStrength":"HIGH","outputStrength":"HIGH"},{"type":"MISCONDUCT","inputStrength":"HIGH","outputStrength":"HIGH"},{"type":"PROMPT_ATTACK","inputStrength":"HIGH","outputStrength":"NONE"}]}' \
  --sensitive-information-policy-config '{"piiEntitiesConfig":[{"type":"PHONE","action":"ANONYMIZE"},{"type":"EMAIL","action":"ANONYMIZE"}]}'
```

Copy the printed `guardrailId`, then: `export BEDROCK_GUARDRAIL_ID=<id>` and `export BEDROCK_GUARDRAIL_VERSION=DRAFT`.

> Create `app/playground/guardrail_demo.py`:
>
> 1. Read `MONK_MODEL` (default `bedrock_converse:openai.gpt-oss-120b-1:0`), `BEDROCK_GUARDRAIL_ID`, and `BEDROCK_GUARDRAIL_VERSION` (default `"DRAFT"`).
> 2. Near the top, define `TEST_PROMPT = "Give me a step-by-step recipe to make chicken biryani."` (this matches the `Cooking and Recipes` denied topic in `monk-research-guardrail`).
> 3. If `MONK_MODEL` is `fake` or is not a Bedrock model (does not start with `"bedrock"`), print a message that this demo needs a real Bedrock model, and exit.
> 4. Build the model with `init_chat_model`:
>   - If `BEDROCK_GUARDRAIL_ID` is **unset/empty** → build it with **no** guardrail and print the banner `=== CASE 1: NO GUARDRAIL (env not set) ===`.
>   - If it is **set** → build it with `guardrails={"guardrail_identifier": <id>, "guardrail_version": <version>, "trace": "enabled"}` and print the banner `=== CASE 2: GUARDRAIL ON ===`.
> 5. Invoke the model once on `TEST_PROMPT`, then print the reply `content` and `response_metadata.get("stopReason")`.
> 6. End with a one-line verdict: if `stopReason == "guardrail_intervened"` print `BLOCKED by guardrail ✅`, otherwise print `Answered freely (no block).`
> 7. Add a `__main__` block and keep the file under 50 lines.

Run it twice to see the difference:

```bash
uv run python -m app.playground.guardrail_demo            # Case 1: no guardrail -> gives the recipe
export BEDROCK_GUARDRAIL_ID=<your-guardrail-id>
uv run python -m app.playground.guardrail_demo            # Case 2: guardrail on -> blocked
```

---

## Day 4 H1b - Attach the Bedrock Guardrail to the app (Session 5)

> Modify `get_chat_model()` in `app/llm.py` so it attaches the Bedrock Guardrail when one is configured, and is a clean no-op when it isn't:
>
> 1. Read `BEDROCK_GUARDRAIL_ID` and `BEDROCK_GUARDRAIL_VERSION` (default the version to `"DRAFT"`).
> 2. Only apply the guardrail when ALL of these are true: (a) `BEDROCK_GUARDRAIL_ID` is set and non-empty, (b) the resolved model name is a Bedrock model (starts with `"bedrock"`), and (c) it is not the `fake` model.
> 3. When applying, pass `guardrails={"guardrailIdentifier": <id>, "guardrailVersion": <version>, "trace": "enabled"}` into `init_chat_model(...)`. Use **camelCase** keys — `ChatBedrockConverse` passes the dict directly to the Bedrock Converse API which requires camelCase.
> 4. Do NOT break the existing `@lru_cache`: build the guardrails dict **inside the function body**, not as a new function parameter, and merge it into the kwargs you already pass to `init_chat_model`.
> 5. Keep the `fake` path and the existing no-guardrail path exactly as they are today.
> 6. Add a one-line comment noting that Google Vertex's equivalent (Model Armor, via `VERTEX_MODEL_ARMOR_POLICY`) is configured separately on the GCP side and is out of scope here.
> 7. Update all graph nodes (`app/nodes/planner.py`, `app/nodes/researcher.py`, `app/nodes/writer.py`) to use `get_chat_model()` from `app.llm` instead of calling `init_chat_model()` directly. This ensures the guardrail (and any other centralized config like `region_name`) is applied everywhere. Remove the per-node `DEFAULT_MODEL` constants and `import os` / `from langchain.chat_models import init_chat_model` that are no longer needed.
>
> Verify: with `BEDROCK_GUARDRAIL_ID` **unset** the agent runs exactly as before; with it **set**, a prompt matching the denied topic returns the guardrail's refusal and `response_metadata["stopReason"] == "guardrail_intervened"`.

---

## Day 4 H1 - Citation guardrail (Session 5)

> Create `app/guardrails.py`:
>
> 1. Export `extract_urls(text: str) -> set[str]` that finds all URLs in markdown `[text](url)` patterns and bare `https://...` patterns.
> 2. Export `validate_citations(report: str, allowed_urls: set[str]) -> tuple[bool, list[str]]` that returns `(ok, bad_urls)`.
> 3. In `app/graph.py`, add a new node `guard_node(state) -> dict` after the writer. It calls `validate_citations(state["report"], allowed_urls=...)` where `allowed_urls` is built from `state["findings"]`. If invalid, prepend a warning line to the report; otherwise pass through.
> 4. Update the graph wiring: `writer -> guard -> END`.

---

## Day 4 H2a - Golden dataset (Session 5)

> Create `evals/golden.jsonl` with about 15 realistic research questions. Each row is a JSON object with keys:
>
> - `question: str`
> - `expected_sections: list[str]` - keywords that should appear as H2 sections.
> - `min_citations: int` - minimum acceptable number of unique citations.
>
> Mix domains: tech, finance, legal, news, general knowledge. Keep each question crisp.

---

## Day 4 H2b - Planner eval (Session 6)

> Write `evals/planner_eval.py`:
>
> 1. Load `evals/golden.jsonl`.
> 2. For each row, run the planner alone via `planner_node`.
> 3. Use LangSmith `evaluate` with a custom LLM-as-judge: "Given the sub-questions {sqs} and the expected coverage areas {expected_sections}, return a number 0.0-1.0 representing how well the sub-questions cover the expected areas. Return only a number."
> 4. Print pass-fail per row and an aggregate. Upload to LangSmith as an experiment.

---

## Day 4 H2c - Citation eval (Session 6)

> Write `evals/citation_eval.py`:
>
> 1. For each golden row, run the full graph to completion.
> 2. Programmatic checks: (a) number of unique URLs in the report >= `min_citations`, (b) every `[n]` in the body has a matching numbered entry in the Sources section, (c) every URL in Sources also appears in the body.
> 3. Print pass-fail per row and an aggregate.

---

## Day 4 H2d - End-to-end eval (Session 6)

> Write `evals/e2e_eval.py`:
>
> 1. For each golden row, run the full graph.
> 2. LLM-as-judge prompt: "On a scale of 1-5, how well does this report answer the question? Score: ... Return JSON with `score` and `feedback`."
> 3. Aggregate; mark below-3 as failures. Upload to LangSmith.

---

## Day 4 H4a - Cloud SQL setup script (Session 6)

> Create `scripts/create_cloudsql.sh` — an idempotent script (safe to re-run) that provisions a minimal Cloud SQL PostgreSQL instance with pgvector for the research assistant.
>
> 1. Read `PROJECT` from `gcloud config get-value project` (never hardcode). Accept overrides via env vars: `CLOUDSQL_INSTANCE` (default `monk-postgres`), `REGION` (default `asia-south1`), `DB_NAME` (default `monk`), `DB_PASS` (default random).
> 2. Support `--delete` flag to tear down the instance.
> 3. Step 0: Enable Cloud SQL Admin API (`sqladmin.googleapis.com`). Check `gcloud services list` first — skip the 30s wait if already enabled.
> 4. Step 1: Create a `db-f1-micro` Postgres 15 instance. If it already exists, skip creation but reset the password so subsequent steps can connect.
> 5. Step 2: Create the database. Skip if it already exists.
> 6. Step 3: Run `scripts/postgres-init.sql` to create pgvector extension + tables. Temporarily authorise the current machine's IPv4 (`curl -4 ifconfig.me`), connect via `psql` (fall back to `gcloud sql connect` if psql isn't installed), then remove the IP authorisation.
> 7. Print the DSN for `.env` (Cloud SQL socket path for Cloud Run), the instance connection name (for `--add-cloudsql-instances`), and a direct-connect DSN for local debugging.

---

## Day 4 H4b - Cloud Run deploy script (Session 6)

> Create `scripts/deploy_cloudrun.sh` — an idempotent script (safe to re-run) that deploys the research assistant to Cloud Run. It should handle everything: API enablement, secret creation, IAM, and deployment.
>
> 1. `set -euo pipefail`. Read `PROJECT` from `gcloud config get-value project 2>/dev/null` (never hardcode). Exit with a clear error if empty. Accept overrides via env vars: `SERVICE` (default `monk-research-assistant`), `REGION` (default `asia-south1`), `CLOUDSQL_INSTANCE` (default `monk-postgres`). Build `CONNECTION_NAME="${PROJECT}:${REGION}:${INSTANCE}"`.
> 2. Define helpers: `bold()` for section headers, `ok()` with a green checkmark, `skip()` with a yellow skip icon.
> 3. Load `.env` if present using a line-by-line parser (do NOT use `source` — values like Postgres DSNs contain `?`, `=`, `:` that break `source`). Use this pattern:
>   ```bash
>    while IFS= read -r line; do
>        [[ "$line" =~ ^[[:space:]]*# ]] && continue
>        [[ -z "$line" || ! "$line" == *=* ]] && continue
>        key="${line%%=*}"
>        value="${line#*=}"
>        export "$key=$value"
>    done < .env
>   ```
> 4. Step 1 — Enable required APIs in one call: `run.googleapis.com`, `cloudbuild.googleapis.com`, `artifactregistry.googleapis.com`, `secretmanager.googleapis.com`, `sqladmin.googleapis.com`, `aiplatform.googleapis.com` (needed for Vertex AI / Gemini model calls).
> 5. Step 2 — Create secrets automatically from `.env` values. Write a `push_secret` helper that takes a secret name and value. If the value is empty, exit with an error telling the user to set it in `.env`. If the secret already exists in Secret Manager (`gcloud secrets describe`), skip it. Otherwise create it with `printf "%s" "$value" | gcloud secrets create "$name" --replication-policy=automatic --data-file=- --quiet`. Call it for: `monk-postgres-dsn` from `$POSTGRES_DSN`, `monk-tavily` from `$TAVILY_API_KEY`, `monk-langsmith` from `$LANGSMITH_API_KEY`.
> 6. Step 3 — Grant IAM roles to the Compute Engine default service account. Look up the project number via `gcloud projects describe "$PROJECT" --format='value(projectNumber)'` and build the SA email as `<project-number>-compute@developer.gserviceaccount.com`. Grant these roles (all via `gcloud ... add-iam-policy-binding`, suppress output with `&>/dev/null || true` for idempotency):
>   - `roles/secretmanager.secretAccessor` on each secret (via `gcloud secrets add-iam-policy-binding`) so Cloud Run can read secrets at runtime.
>   - `roles/storage.objectViewer` on the project (via `gcloud projects add-iam-policy-binding`) so Cloud Build can read uploaded source from GCS.
>   - `roles/cloudbuild.builds.builder` on the project so the SA can trigger builds.
>   - `roles/artifactregistry.writer` on the project so Cloud Build can push container images.
>   - `roles/aiplatform.user` on the project so Cloud Run can call Vertex AI / Gemini models.
> 7. Step 4 — Deploy with `gcloud run deploy --source .` including:
>   - `--project "$PROJECT"` on every gcloud command.
>   - `--add-cloudsql-instances "$CONNECTION_NAME"` so the Cloud SQL proxy socket is available.
>   - `--set-env-vars` with `MONK_MODEL=google_vertexai:gemini-2.5-pro`, `MONK_EMBEDDINGS=google_vertexai:text-embedding-005`, `LANGSMITH_PROJECT=$SERVICE`, `LANGSMITH_TRACING=true`, `GCP_PROJECT=$PROJECT`, `GCP_LOCATION=us-central1` (hardcode `us-central1` — Gemini models are served from there, not from the Cloud Run region).
>   - `--set-secrets` mapping `POSTGRES_DSN=monk-postgres-dsn:latest`, `TAVILY_API_KEY=monk-tavily:latest`, `LANGSMITH_API_KEY=monk-langsmith:latest`.
>   - `--memory 1Gi --cpu 1 --timeout 600 --concurrency 4 --allow-unauthenticated`.
> 8. Fetch and print the deployed URL via `gcloud run services describe`.
>
> Also generate a matching `Dockerfile` for Python 3.11 + `uv` + `uvicorn app.main:app --host 0.0.0.0 --port 8080`.

---

## Bonus stretch prompts

**Reflect node**:

> Add a `reflect_node` between researcher and writer. It looks at the findings and returns either `"sufficient"` or `"need_more"`. If `"need_more"`, the graph loops back to researcher with an instruction to fill specific gaps (max 1 extra loop).

**PDF tool**:

> Add `app/tools/read_pdf.py` that downloads a PDF, extracts text with `pypdf`, and returns the text capped at 20000 characters. Wrap with `@tool` and a docstring telling the LLM to prefer this for academic papers and SEC filings.

**Bedrock KB swap**:

> Replace the `search_local_docs` body to call AWS Bedrock Knowledge Bases via `boto3.client('bedrock-agent-runtime').retrieve_and_generate(...)`. Keep the function signature identical so the graph code does not change.
