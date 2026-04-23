import asyncio
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

# workflow.unsafe.imports_passed_through() tells the Temporal sandbox to pass
# these imports through without determinism-checking. Activity modules pull in
# vaderSentiment, sqlite3, and asyncio.sleep — all non-deterministic from the
# sandbox's perspective, but safe because they only run in activity code.
with workflow.unsafe.imports_passed_through():
    from activities.scrape_reviews import scrape_reviews_activity
    from activities.analyze_sentiment import analyze_sentiment_activity
    from activities.store_results import store_results_activity
    from models.data_models import (
        AverageResult,
        ProductConfig,
        Review,
        SentimentBreakdown,
        SentimentScore,
        WorkflowProgress,
    )

# Retry policies defined as module-level constants so they're easy to tune and
# clearly visible during a code review or interview walkthrough.
_SCRAPE_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
)

_SENTIMENT_RETRY = RetryPolicy(
    maximum_attempts=2,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=1.5,
)

_STORE_RETRY = RetryPolicy(
    maximum_attempts=5,
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
)


@workflow.defn
class SentimentAnalysisWorkflow:
    """Orchestrates the full review → sentiment → storage pipeline.

    Stages:
      1. scrape_reviews_activity   — fan-in a list of Review objects
      2. analyze_sentiment_activity (fan-out) — one activity per review, parallel
      3. aggregate                 — pure Python avg/breakdown, no activity needed
      4. store_results_activity    — persist to SQLite

    A Query handler exposes live progress so callers can poll without blocking.
    """

    def __init__(self) -> None:
        self._progress = WorkflowProgress(
            stage="starting",
            reviews_scraped=0,
            reviews_analyzed=0,
            message="Workflow initialized",
        )

    @workflow.query
    def get_progress(self) -> WorkflowProgress:
        """Return current workflow stage without interrupting execution."""
        return self._progress

    @workflow.run
    async def run(self, config: ProductConfig) -> AverageResult:

        # ── Stage 1: Scrape ──────────────────────────────────────────────────
        self._progress = WorkflowProgress(
            stage="scraping",
            reviews_scraped=0,
            reviews_analyzed=0,
            message=f"Scraping reviews for '{config.product_name}' via {config.scraper_type}",
        )
        workflow.logger.info("Stage: scraping — product_id=%s scraper=%s",
                             config.product_id, config.scraper_type)

        reviews: list[Review] = await workflow.execute_activity(
            scrape_reviews_activity,
            config,
            start_to_close_timeout=timedelta(seconds=120),
            # If the worker stops heartbeating for 10 s, Temporal retries the
            # activity on another worker — much faster than waiting the full
            # start_to_close_timeout to detect a crash.
            heartbeat_timeout=timedelta(seconds=10),
            retry_policy=_SCRAPE_RETRY,
        )

        # ── Stage 2: Fan-out sentiment analysis ──────────────────────────────
        self._progress = WorkflowProgress(
            stage="analyzing",
            reviews_scraped=len(reviews),
            reviews_analyzed=0,
            message=f"Analyzing sentiment for {len(reviews)} reviews",
        )
        workflow.logger.info("Stage: analyzing — reviews=%d", len(reviews))

        # asyncio.gather fires all N activity executions simultaneously.
        # Each review is an independent unit of work and can be retried on its
        # own if it fails — this is one of Temporal's core reliability benefits.
        sentiment_tasks = [
            workflow.execute_activity(
                analyze_sentiment_activity,
                review,
                start_to_close_timeout=timedelta(seconds=30),
                heartbeat_timeout=timedelta(seconds=10),
                retry_policy=_SENTIMENT_RETRY,
            )
            for review in reviews
        ]
        scores: list[SentimentScore] = list(await asyncio.gather(*sentiment_tasks))

        # ── Stage 3: Fan-in / aggregate ───────────────────────────────────────
        # Pure arithmetic — no I/O, so it lives in the workflow, not an activity.
        self._progress = WorkflowProgress(
            stage="storing",
            reviews_scraped=len(reviews),
            reviews_analyzed=len(scores),
            message=f"Aggregating {len(scores)} scores and storing results",
        )
        workflow.logger.info("Stage: storing — scores=%d", len(scores))

        avg_compound = sum(s.compound for s in scores) / len(scores)
        breakdown = SentimentBreakdown(
            positive_count=sum(1 for s in scores if s.compound > 0.05),
            negative_count=sum(1 for s in scores if s.compound < -0.05),
            neutral_count=sum(1 for s in scores if -0.05 <= s.compound <= 0.05),
        )
        result = AverageResult(
            product_id=config.product_id,
            product_name=config.product_name,
            avg_compound=avg_compound,
            review_count=len(scores),
            breakdown=breakdown,
            scores=scores,
            reviews=reviews,
            source=config.scraper_type,
        )

        # ── Stage 4: Store ───────────────────────────────────────────────────
        stored_result: AverageResult = await workflow.execute_activity(
            store_results_activity,
            result,
            start_to_close_timeout=timedelta(seconds=60),
            heartbeat_timeout=timedelta(seconds=15),
            retry_policy=_STORE_RETRY,
        )

        self._progress = WorkflowProgress(
            stage="done",
            reviews_scraped=len(reviews),
            reviews_analyzed=len(scores),
            message=f"Complete. avg_compound={avg_compound:.4f} over {len(scores)} reviews",
        )
        workflow.logger.info("Stage: done — avg_compound=%+.4f reviews=%d run_id=%s",
                             avg_compound, len(scores), stored_result.run_id)

        return stored_result
