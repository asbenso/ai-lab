# Warm-up prompts (Sessions 1-2 foundations)

These prompts cover Session 1 / Day 1 H4 ("Hello Agent") and all of Session 2 / Day 2 (function calling + RAG). They live in the Project 1 repo because the Project 1 graph reuses these tools verbatim.

> **Session mapping**: Session 1 = Day 1 slides (D1.x). Session 2 = Day 2 slides (D2.x). Prompt IDs like `Day 1 H4` are stable references used in notes, teaching scripts, and BUILD_REFERENCEs.

---

## Day 1 H4 - Hello Agent (Session 1)

**Goal**: a 30-line tool-using bot that runs on Bedrock AND Vertex by changing `MONK_MODEL`.

**Prompt**:

> Create `app/hello_agent.py`. It should:
>
> 1. Use LangChain `init_chat_model` with model name from env var `MONK_MODEL` (default `bedrock_converse:openai.gpt-oss-120b-1:0`).
> 2. Define two `@tool` decorated functions: `get_weather(city: str)` returns the canned string `"It's 28C and sunny in {city}."`, and `search_news(topic: str)` returns the canned string `"Top story on {topic}: AI agents are eating tools."`.
> 3. Bind both tools to the model with `.bind_tools(...)`.
> 4. Define an `agent_run(question: str)` function that loops up to 6 iterations: invoke the model on the running messages list, if the response has `tool_calls` then execute each one and append a `ToolMessage`, otherwise return `ai_msg.content`.
> 5. In `__main__`, call `agent_run("What is the weather in Bangalore today and what's the latest AI news?")` and print the answer.
>
> Use type hints. Keep it under 80 lines. Use only `langchain`, `langchain-core`, and stdlib.

**Follow-ups likely**:

- "Add a third tool `get_time(timezone: str)` that returns the current ISO time in the given IANA timezone."
- "Print the number of tool calls used at the end."

---

## Day 2 H2 - Three real tools (Session 2)

**Goal**: real `web_search`, `fetch_url`, `summarize` tools that Project 1 will use.

**Prompt**:

> Create three files in `app/tools/`:
>
> 1. `web_search.py` - export `web_search(query: str, k: int = 5) -> list[dict]`. Use the Tavily Python client (`tavily-python`). Each result dict has keys `title`, `url`, `content`. Get the API key from `TAVILY_API_KEY`. If the key is missing, return one fake `{"title": "mock", "url": "https://example.com", "content": query}` so labs still run.
>
> 2. `fetch_url.py` - export `fetch_url(url: str) -> str`. Use `httpx` with a 10-second timeout and a browser user-agent. Strip HTML with `BeautifulSoup`. Cap the returned content at 8000 characters. Return a string starting with `"[Source: {url}]\n"`.
>
> 3. `summarize.py` - export `summarize(text: str, focus: str = "") -> str`. Use `init_chat_model` (model from env var `MONK_MODEL`) to produce a 3-sentence summary. If `focus` is non-empty, the summary must emphasise it.
>
> Each function should be wrapped with `@tool` from `langchain_core.tools` and have a docstring written for an LLM reader (clear, single sentence on what it does and when to use it). Use type hints throughout. Add a `__main__` smoke test in each file.

**Follow-ups likely**:

- "Add a retry with exponential backoff to `fetch_url`."
- "Make `web_search` configurable to use SerpAPI as fallback when Tavily is missing."

---

## Day 2 H3 - Ingestion sanity demo (Session 2)

**Goal**: students see the chunk + embed + upsert flow.

**Prompt** (a small one, since the production scripts ship in the starter repo):

> In a scratch file `app/playground/demo_embedding.py`, write a 20-line script that:
>
> 1. Loads two text chunks from `data/sample-corpus/aws-docs/iam-rotation.md` (just read the file and split by `\n\n`).
> 2. Embeds them with `init_embeddings("bedrock:amazon.titan-embed-text-v2:0")`.
> 3. Prints the cosine similarity between the two embeddings.
>
> The goal is to make embeddings feel concrete.

---

## Day 2 H4 - search_local_docs tool (Session 2)

**Goal**: the retrieval tool Project 1 will hand to its Researcher.

**Prompt**:

> Create `app/tools/search_local_docs.py`. Export `search_local_docs(query: str, k: int = 5, table: str = "docs") -> list[dict]`.
>
> 1. Connect to Postgres via `psycopg` (sync is fine) using `POSTGRES_DSN` env var.
> 2. Embed the query with the embeddings model from `MONK_EMBEDDINGS` (default `bedrock:amazon.titan-embed-text-v2:0`), using `init_embeddings`.
> 3. Run `SELECT chunk_id, source_url, 1 - (embedding <=> %s::vector) AS score, text FROM {table} ORDER BY embedding <=> %s::vector LIMIT %s` (sanitise the table name).
> 4. Return `[{"chunk_id": str, "source_url": str, "score": float, "text": str}, ...]`.
> 5. Wrap with `@tool` from `langchain_core.tools`. Docstring: "Search the ingested document corpus for content relevant to a query. Use this when the user asks about content in our internal documentation. Returns a list of citations each with a real source_url that you MUST cite back."

**Follow-ups likely**:

- "Add an optional `filter_source: str | None` parameter that prefixes the query with `WHERE source_url LIKE %s`."
- "Add a max_score threshold and skip rows below it."
