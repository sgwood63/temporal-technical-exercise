# Plan: Temporal SA Technical Exercise — Product Review Sentiment Pipeline

## Context
This is a Solution Architect interview exercise for Temporal. The goal is to demonstrate understanding of Temporal's core patterns (workflows, activities, retries, heartbeating, fan-out/fan-in, queries) using a real-world data pipeline scenario. External integrations (web scraping) are intentionally mocked per the exercise FAQ. Code must run end-to-end; production hardening (Docker, CI/CD) is out of scope.

**Chosen use case:** Scrape product reviews → run sentiment analysis → average scores → store results.

**Review source: Amazon** — Amazon was chosen over Etsy because it has more standardized review structure (star rating 1–5, title, body, verified purchase badge), larger review volumes, and more recognizable products for demo purposes. Real Amazon scraping would use Playwright to handle JavaScript-rendered review carousels; for this exercise the structure is mocked but mirrors the actual Amazon review schema exactly so the workflow design generalizes directly.

---

## File Structure

```
temporal-technical-exercise/
├── CLAUDE.md
├── README.md                  # update with diagram + run instructions
├── requirements.txt
├── .env.example
├── run_workflow.py             # workflow starter + --query-only flag
├── worker.py                   # polls task queue, inits DB
├── workflows/
│   ├── __init__.py
│   └── sentiment_workflow.py
├── activities/
│   ├── __init__.py
│   ├── scrape_reviews.py       # activity wrapper — delegates to scraper plugin
│   ├── analyze_sentiment.py    # VADER per-review
│   └── store_results.py        # SQLite
├── scrapers/
│   ├── __init__.py
│   ├── base.py                 # ReviewScraper Protocol (abstract interface)
│   ├── mock_scraper.py         # default: deterministic mock Amazon reviews
│   ├── amazon_scraper.py       # stub: shows how real Playwright scraper fits
│   └── registry.py             # maps scraper_type string → class
├── models/
│   ├── __init__.py
│   └── data_models.py          # all dataclasses
└── db/
    ├── __init__.py
    └── init_db.py              # schema creation
```

---

## Implementation Steps

### Step 1 — `models/data_models.py`
Define all dataclasses (JSON-serializable, no datetime objects — use ISO strings):
- `ProductConfig` — workflow input: `product_name`, `product_id`, `source_url`, `max_reviews`, `scraper_type: str = "mock"` (selects which plugin to use)
- `Review` — scraped review: `review_id`, `product_id`, `reviewer`, `rating`, `title`, `text`, `date`, `source`, `verified_purchase`
- `SentimentScore` — per-review VADER output: `review_id`, `compound`, `positive`, `negative`, `neutral`
- `SentimentBreakdown` — `positive_count`, `negative_count`, `neutral_count`
- `AverageResult` — final workflow output: `product_id`, `product_name`, `avg_compound`, `review_count`, `breakdown`, `scores`, `run_id`
- `WorkflowProgress` — query response: `stage`, `reviews_scraped`, `reviews_analyzed`, `message`

### Step 2 — `db/init_db.py`
SQLite schema, called once at worker startup:
- `analysis_runs(id, product_id, product_name, run_at, review_count, avg_score, status)`
- `reviews(id, run_id, review_id, reviewer, rating, title, text, date, source, verified)`
- `sentiment_scores(id, review_id, run_id, compound, positive, negative, neutral)`

### Step 3 — Pluggable scraper layer (`scrapers/`)

**`scrapers/base.py`** — `ReviewScraper` Protocol:
```python
class ReviewScraper(Protocol):
    async def scrape(self, config: ProductConfig, heartbeat_fn: Callable) -> list[Review]: ...
    @property
    def source_name(self) -> str: ...
```
All scrapers implement this interface. The `heartbeat_fn` callback is passed in so the activity controls heartbeating independent of scraper logic.

**`scrapers/mock_scraper.py`** — default implementation:
- `source_name = "amazon_mock"`
- Seeded `random.Random(f"{config.product_id}-page-{page}")` → deterministic, idempotent across retries
- Realistic corpus of ~15 Amazon review templates spanning full sentiment range (1–5 stars, varied text)
- `asyncio.sleep(2)` per page to simulate network latency, triggering the heartbeat callback

**`scrapers/amazon_scraper.py`** — real scraper stub:
- `source_name = "amazon"`
- Shows how Playwright would navigate `amazon.com/product-reviews/<ASIN>`, parse review HTML, and return `list[Review]`
- Raises `NotImplementedError` with a descriptive message — shows the interface is ready to be filled in
- Includes inline comments on what CSS selectors to use and how to handle pagination

**`scrapers/registry.py`** — maps `scraper_type` string to class:
```python
SCRAPERS: dict[str, type[ReviewScraper]] = {
    "mock": MockScraper,
    "amazon": AmazonScraper,
}
def get_scraper(scraper_type: str) -> ReviewScraper: ...
```

**`activities/scrape_reviews.py`** — thin activity wrapper:
- `@activity.defn` async function
- Calls `get_scraper(config.scraper_type)` from the registry
- Wraps `activity.heartbeat(...)` into a callback passed to `scraper.scrape(config, heartbeat_fn)`
- `start_to_close_timeout=120s`, `heartbeat_timeout=10s`, retry_policy=3 attempts exp backoff
- `source` field on every `Review` comes from `scraper.source_name` — ties stored data back to the plugin used

### Step 4 — `activities/analyze_sentiment.py`
- `@activity.defn` async function
- Module-level `_analyzer = SentimentIntensityAnalyzer()` (load VADER lexicon once per worker process)
- Combines `review.title + ". " + review.text` for richer signal
- Returns `SentimentScore` with all four VADER scores

### Step 5 — `activities/store_results.py`
- `@activity.defn` async function
- Inserts into `analysis_runs` then `sentiment_scores`; populates `result.run_id` from `lastrowid`
- Returns modified `AverageResult` (so caller sees the DB-assigned `run_id`)

### Step 6 — `workflows/sentiment_workflow.py`
Key patterns demonstrated:
- `workflow.unsafe.imports_passed_through()` — sandbox-safe import of activity modules
- Module-level `RetryPolicy` constants for scrape (3 attempts, exp backoff), sentiment (2 attempts), store (5 attempts)
- `@workflow.query` — synchronous `get_progress()` returning `WorkflowProgress`
- Stage 1: `execute_activity(scrape_reviews_activity, config, start_to_close_timeout=120s, heartbeat_timeout=10s, retry_policy=SCRAPE_RETRY_POLICY)`
- Stage 2 fan-out: `asyncio.gather(*[execute_activity(analyze_sentiment_activity, r, start_to_close_timeout=30s) for r in reviews])`
- Stage 3 fan-in: pure Python avg + breakdown calculation **inside the workflow** (no activity — pure math, no I/O)
- Stage 4: `execute_activity(store_results_activity, result, start_to_close_timeout=60s)`
- Mutates `self._progress` between stages so Query handler reflects live state

### Step 7 — `worker.py`
- Calls `init_db()` before polling
- Connects to Temporal Cloud: `Client.connect(address, namespace=..., tls=TLSConfig(domain=...), api_key=...)`
- `Worker(client, task_queue=TASK_QUEUE, workflows=[SentimentAnalysisWorkflow], activities=[...])`

### Step 8 — `run_workflow.py`
- `--query-only <workflow-id>` flag to demo Query handler against a running workflow
- Default product: Sony WH-1000XM5 Headphones (concrete, recognizable)
- Prints formatted results on completion

### Step 9 — Supporting files
- `requirements.txt`: `temporalio>=1.6.0`, `vaderSentiment>=3.3.2`, `python-dotenv>=1.0.0`
- `.env.example`: `TEMPORAL_ADDRESS`, `TEMPORAL_NAMESPACE`, `TEMPORAL_API_KEY`, `TASK_QUEUE`, `DB_PATH`
- `CLAUDE.md`: determinism rules, import rules, patterns to preserve
- `README.md` update: Mermaid architecture diagram, prerequisites, two-terminal run instructions

---

## Architecture Diagram (for README)

```
flowchart TD
    A[run_workflow.py] -->|ProductConfig| B[Temporal Cloud]
    B --> C[SentimentAnalysisWorkflow]
    C --> D[scrape_reviews_activity\nHeartbeats / 3 retries]
    D -->|list[Review]| E{Fan-out\nasyncio.gather}
    E --> F1[analyze_sentiment\nReview 1]
    E --> F2[analyze_sentiment\nReview 2]
    E --> F3[analyze_sentiment\nReview N]
    F1 --> G{Fan-in\nAggregate in workflow}
    F2 --> G
    F3 --> G
    G --> H[store_results_activity\nSQLite]
    H --> I[AverageResult returned]
    J[Query: get_progress] -.->|WorkflowProgress| C
    H --> K[(SQLite DB)]
```

---

## Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Serialization | `dataclasses` (not Pydantic) | Temporal SDK natively handles dataclasses; minimal deps |
| Scraping | Pluggable `ReviewScraper` Protocol; `MockScraper` default | FAQ says to mock; plugin pattern lets real scrapers slot in without changing the activity or workflow; seeded random = idempotent retries |
| Sentiment | VADER | No model training, handles informal review text, fast, pure Python |
| Storage | SQLite | Zero-config, stdlib, sufficient for demo |
| Aggregation | Inside workflow | Pure math = no I/O → belongs in workflow, not activity |
| Fan-out scope | Per-review activities | Demonstrates parallelism; each review independently retryable |

---

## Verification

```bash
# Terminal 1 — start worker
python worker.py

# Terminal 2 — run full pipeline, wait for result
python run_workflow.py

# Terminal 2 — query a running workflow (run in parallel with long max_reviews run)
python run_workflow.py --max-reviews 50 &
python run_workflow.py --query-only sentiment-sony-wh1000xm5-<id>

# Verify DB was written
sqlite3 sentiment_results.db "SELECT * FROM analysis_runs;"
```

Also visible in Temporal Cloud UI: workflow event history showing `ActivityTaskScheduled` fan-out, heartbeat events, and Query responses.

---

## Post-Implementation: Temporal Skill Review

After the initial implementation, a Temporal SDK best-practice review identified the following gaps and drove the changes below. Each item maps a concrete Temporal failure mode to the code change that closes it.

### 1. Heartbeating incomplete — sentiment and store activities

**Gap:** `heartbeat_timeout` was set only for `scrape_reviews_activity`, and only the scrape activity called `activity.heartbeat()`. The two other activities had neither.

**Why it matters:** `heartbeat_timeout` is Temporal's mechanism for detecting that a worker has crashed mid-activity. If the worker process dies while running `analyze_sentiment_activity` or `store_results_activity`, Temporal has no signal that anything is wrong until `start_to_close_timeout` expires — 30 s and 60 s respectively. For the fan-out sentiment phase, that means all N parallel activities could all silently stall for 30 s before any retry begins.

**Change:**
- `analyze_sentiment_activity` — added `activity.heartbeat({"review_id": ...})` call; added `heartbeat_timeout=timedelta(seconds=10)` to its `execute_activity` call in the workflow.
- `store_results_activity` — added `activity.heartbeat({"reviews_inserted": i + 1})` every 50 rows in the review insert loop; added `heartbeat_timeout=timedelta(seconds=15)` to its `execute_activity` call.

**Files:** `activities/analyze_sentiment.py`, `activities/store_results.py`, `workflows/sentiment_workflow.py`

---

### 2. `_SENTIMENT_RETRY` missing `backoff_coefficient`

**Gap:** `_SENTIMENT_RETRY` had no `backoff_coefficient`, defaulting to `1.0` (fixed-interval retries).

**Why it matters:** Fixed-interval retries create correlated retry storms. All N fan-out sentiment activities that fail at the same instant retry at the same instant, potentially recreating the same failure condition. The other two retry policies (`_SCRAPE_RETRY`, `_STORE_RETRY`) already set `backoff_coefficient=2.0` — the omission was an oversight.

**Change:** Added `backoff_coefficient=1.5` to `_SENTIMENT_RETRY`.

**File:** `workflows/sentiment_workflow.py`

---

### 3. Worker unbounded concurrency

**Gap:** The `Worker` constructor specified no `max_concurrent_activity_task_executions` or `max_concurrent_workflow_task_executions`.

**Why it matters:** Temporal's worker will accept as many tasks as the server sends. A workflow with 500 reviews schedules 500 concurrent `analyze_sentiment_activity` tasks. The worker pulls all 500 simultaneously, loading 500 VADER analyses into memory at once. This can OOM a modest worker process and creates unpredictable latency spikes.

**Change:** Set `max_concurrent_activity_task_executions=50` and `max_concurrent_workflow_task_executions=10`. Excess tasks remain in the Temporal task queue until the worker has capacity — Temporal handles backpressure automatically.

**File:** `worker.py`

---

### 4. Store activity not idempotent

**Gap:** `store_results_activity` did a plain `INSERT INTO analysis_runs` with no deduplication.

**Why it matters:** Temporal guarantees *at-least-once* activity execution, not *exactly-once*. If the worker commits the SQLite transaction but crashes before it can report completion to the Temporal server, Temporal schedules a retry. The retry runs the full insert again, creating a second `analysis_runs` row for the same workflow run. This is a silent correctness bug: no error is raised, but historical aggregations over `analysis_runs` are wrong.

**Change:**
- Added `workflow_run_id TEXT` column to `analysis_runs` with a partial unique index (`WHERE workflow_run_id IS NOT NULL`).
- `store_results_activity` reads `activity.info().workflow_run_id`, checks for an existing row before inserting, and returns the existing `run_id` if found.
- `init_db()` includes a migration step (`ALTER TABLE ... ADD COLUMN`) for existing databases.

**Files:** `activities/store_results.py`, `db/init_db.py`

---

### 5. `ApplicationError(non_retryable=True)` for configuration errors

**Gap:** An unknown `scraper_type` raised a plain `ValueError` from the registry, which Temporal treats as retryable. All 3 scrape retry attempts would be consumed before the workflow failed.

**Why it matters:** A misconfigured `scraper_type` is not a transient fault — no amount of retrying will fix it. Consuming the full retry budget adds latency, generates noise in the event history, and delays the error signal to the caller.

**Change:** `scrape_reviews_activity` wraps the registry lookup in a `try/except ValueError` and re-raises as `ApplicationError(str(exc), non_retryable=True)`. Temporal fails the activity on the first attempt and propagates the error immediately.

**File:** `activities/scrape_reviews.py`

---

### 6. Dataclass input validation

**Gap:** `ProductConfig` and `Review` had no `__post_init__` validation.

**Why it matters:** Invalid values (e.g., `max_reviews=0`, `rating=6`) are serialized into the workflow history and only cause errors deep in the pipeline — an `ZeroDivisionError` in the aggregation stage or a constraint violation in SQLite — rather than a clear failure at the input boundary.

**Change:** Added `__post_init__` to `ProductConfig` (validates `max_reviews >= 1`, non-empty `product_id`) and `Review` (validates `1 <= rating <= 5`). Errors surface as `ValueError` before the workflow is started.

**File:** `models/data_models.py`

---

### 7. Database indexes and foreign key enforcement

**Gap:** The SQLite schema had no indexes on join columns and never enabled `PRAGMA foreign_keys`.

**Why it matters:** SQLite disables FK enforcement by default — referential integrity violations (e.g., orphaned `reviews` rows) silently succeed. Without indexes on `reviews.run_id` and `sentiment_scores.run_id`, any query joining these tables requires a full table scan, degrading with data volume.

**Change:** Added `CREATE INDEX IF NOT EXISTS` on both join columns; added `PRAGMA foreign_keys = ON` in `init_db()` and in each connection opened by `store_results_activity`.

**File:** `db/init_db.py`

---

### Summary of files changed

| File | Change |
|---|---|
| `workflows/sentiment_workflow.py` | `heartbeat_timeout` on sentiment + store; `backoff_coefficient` on `_SENTIMENT_RETRY` |
| `activities/analyze_sentiment.py` | `activity.heartbeat()` call |
| `activities/store_results.py` | `activity.heartbeat()` in insert loop; idempotency guard using `workflow_run_id` |
| `activities/scrape_reviews.py` | `ApplicationError(non_retryable=True)` for unknown scraper type |
| `worker.py` | `max_concurrent_activity_task_executions=50`, `max_concurrent_workflow_task_executions=10` |
| `db/init_db.py` | `workflow_run_id` column; partial unique index; join indexes; FK enforcement; migration |
| `models/data_models.py` | `__post_init__` validation on `ProductConfig` and `Review` |
| `tests/test_workflow.py` | Three new tests: `test_dataclass_validation`, `test_invalid_scraper_type`, `test_store_activity_idempotency` |
