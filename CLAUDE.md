# CLAUDE.md — Claude Code Guidelines

## Project Purpose
Temporal Python SDK demo for the SA Technical Interview exercise.
Pipeline: scrape Amazon reviews → VADER sentiment analysis → aggregate → SQLite.

## Architecture Rules

**Workflow determinism**
- Workflows MUST be deterministic. Never use `random`, `datetime.now()`, `time.time()`, or any I/O inside `@workflow.run`.
- All side effects (network, disk, sleep, randomness) MUST live in `@activity.defn` functions.
- The `workflow.unsafe.imports_passed_through()` block in `sentiment_workflow.py` is required — do not remove it. Activity modules import `vaderSentiment` and `sqlite3`, which the Temporal sandbox would otherwise reject.

**Activities**
- Every `@activity.defn` is a standalone async function in `activities/`.
- Long-running activities MUST call `activity.heartbeat(state_dict)` so Temporal can detect worker crashes. The heartbeat_timeout on `scrape_reviews_activity` is set to 10 s; the mock scraper heartbeats every page (~1 s), so there is plenty of margin.
- Do NOT call `activity.heartbeat()` from workflow code — only from within an activity.

**Scraper plugins**
- All scrapers implement the `ReviewScraper` Protocol from `scrapers/base.py`.
- The `heartbeat_fn` callback is passed from the activity to the scraper — scrapers never import `temporalio.activity` directly.
- `MockScraper` uses seeded `random.Random(product_id + page)` — keep this deterministic so the activity is idempotent across retries.
- To add a new site: create `scrapers/<site>_scraper.py`, implement the Protocol, and add it to `scrapers/registry.py`.

**Data models**
- All dataclasses live in `models/data_models.py` — do not scatter them.
- Field types must be JSON-serializable (str, int, float, bool, list, dict). No `datetime` objects — use ISO 8601 strings.
- Do not introduce Pydantic — the Temporal Python SDK handles dataclasses natively.

## Retry Policies
Defined as module-level constants in `workflows/sentiment_workflow.py`:
- `_SCRAPE_RETRY`: 3 attempts, exp backoff, 30 s max interval
- `_SENTIMENT_RETRY`: 2 attempts, 2 s initial
- `_STORE_RETRY`: 5 attempts, exp backoff, 60 s max interval

Do not inline retry policies in `execute_activity` calls — keep them as named constants.

## Running the Project

```bash
# Terminal 1 — start the worker
python worker.py

# Terminal 2 — run a workflow and wait for the result
python run_workflow.py

# Terminal 2 — query a running workflow's progress
python run_workflow.py --query-only <workflow-id>
```

## Do Not
- Do not add Docker, CI/CD, Kubernetes manifests, or deployment scripts
- Do not make real HTTP requests to Amazon (use `scraper_type=mock`)
- Do not commit `.env` — it contains secrets
- Do not add error handling for scenarios that can't happen (trust dataclass validation, trust Temporal retries)
- Do not add comments explaining WHAT the code does — only WHY when non-obvious
