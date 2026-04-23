import sqlite3
from unittest.mock import MagicMock, patch

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ActivityError, ApplicationError
from temporalio.worker import Worker

from activities.scrape_reviews import scrape_reviews_activity
from models.data_models import (
    AverageResult,
    ProductConfig,
    Review,
    SentimentBreakdown,
    SentimentScore,
    WorkflowProgress,
)
from workflows.sentiment_workflow import SentimentAnalysisWorkflow

from .conftest import TASK_QUEUE, unique_workflow_id


# ── Mock review builder ──────────────────────────────────────────────────────

def _make_reviews(config: ProductConfig) -> list[Review]:
    return [
        Review(
            review_id=f"test-review-{i}",
            product_id=config.product_id,
            reviewer=f"Reviewer {i}",
            rating=4,
            title="Good product",
            text="Works as expected.",
            date="2025-01-01",
            source="test",
            verified_purchase=True,
        )
        for i in range(config.max_reviews)
    ]


# ── Activity factories ───────────────────────────────────────────────────────

def make_scrape_activity(fail_times: int):
    state = {"calls": 0}

    @activity.defn(name="scrape_reviews_activity")
    async def mock_scrape(config: ProductConfig) -> list[Review]:
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise ApplicationError("simulated scrape failure")
        return _make_reviews(config)

    return mock_scrape


def make_sentiment_activity(fail_times: int):
    """Track failures per review_id so fan-out parallelism is deterministic."""
    counts: dict[str, int] = {}

    @activity.defn(name="analyze_sentiment_activity")
    async def mock_sentiment(review: Review) -> SentimentScore:
        n = counts.get(review.review_id, 0) + 1
        counts[review.review_id] = n
        if n <= fail_times:
            raise ApplicationError(f"simulated sentiment failure for {review.review_id}")
        return SentimentScore(
            review_id=review.review_id,
            compound=0.5,
            positive=0.5,
            negative=0.0,
            neutral=0.5,
        )

    return mock_sentiment


def make_store_activity(fail_times: int):
    state = {"calls": 0}

    @activity.defn(name="store_results_activity")
    async def mock_store(result: AverageResult) -> AverageResult:
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise ApplicationError("simulated store failure")
        result.run_id = "test-run-1"
        return result

    return mock_store


# ── Tests ────────────────────────────────────────────────────────────────────

async def test_happy_path(workflow_env, product_config):
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            make_scrape_activity(0),
            make_sentiment_activity(0),
            make_store_activity(0),
        ],
    ):
        result: AverageResult = await workflow_env.client.execute_workflow(
            SentimentAnalysisWorkflow.run,
            product_config,
            id=unique_workflow_id("happy-path"),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, AverageResult)
    assert result.review_count == product_config.max_reviews
    assert result.run_id == "test-run-1"
    total = (
        result.breakdown.positive_count
        + result.breakdown.negative_count
        + result.breakdown.neutral_count
    )
    assert total == result.review_count


async def test_scrape_occasional_failure(workflow_env, product_config):
    """Scrape fails twice (within 3-attempt limit) then succeeds."""
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            make_scrape_activity(2),
            make_sentiment_activity(0),
            make_store_activity(0),
        ],
    ):
        result: AverageResult = await workflow_env.client.execute_workflow(
            SentimentAnalysisWorkflow.run,
            product_config,
            id=unique_workflow_id("scrape-occasional"),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, AverageResult)
    assert result.review_count == product_config.max_reviews


async def test_sentiment_occasional_failure(workflow_env, product_config):
    """Each review's sentiment activity fails once (within 2-attempt limit) then succeeds."""
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            make_scrape_activity(0),
            make_sentiment_activity(1),
            make_store_activity(0),
        ],
    ):
        result: AverageResult = await workflow_env.client.execute_workflow(
            SentimentAnalysisWorkflow.run,
            product_config,
            id=unique_workflow_id("sentiment-occasional"),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, AverageResult)
    assert result.review_count == product_config.max_reviews


async def test_store_occasional_failure(workflow_env, product_config):
    """Store fails 4 times (within 5-attempt limit) then succeeds."""
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            make_scrape_activity(0),
            make_sentiment_activity(0),
            make_store_activity(4),
        ],
    ):
        result: AverageResult = await workflow_env.client.execute_workflow(
            SentimentAnalysisWorkflow.run,
            product_config,
            id=unique_workflow_id("store-occasional"),
            task_queue=TASK_QUEUE,
        )

    assert isinstance(result, AverageResult)
    assert result.run_id == "test-run-1"


async def test_scrape_final_failure(workflow_env, product_config):
    """Scrape exhausts all 3 attempts — workflow fails."""
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            make_scrape_activity(99),
            make_sentiment_activity(0),
            make_store_activity(0),
        ],
    ):
        with pytest.raises(WorkflowFailureError):
            await workflow_env.client.execute_workflow(
                SentimentAnalysisWorkflow.run,
                product_config,
                id=unique_workflow_id("scrape-final"),
                task_queue=TASK_QUEUE,
            )


async def test_sentiment_final_failure(workflow_env, product_config):
    """Each review's sentiment activity exhausts both attempts — workflow fails."""
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            make_scrape_activity(0),
            make_sentiment_activity(2),
            make_store_activity(0),
        ],
    ):
        with pytest.raises(WorkflowFailureError):
            await workflow_env.client.execute_workflow(
                SentimentAnalysisWorkflow.run,
                product_config,
                id=unique_workflow_id("sentiment-final"),
                task_queue=TASK_QUEUE,
            )


async def test_store_final_failure(workflow_env, product_config):
    """Store exhausts all 5 attempts — workflow fails."""
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            make_scrape_activity(0),
            make_sentiment_activity(0),
            make_store_activity(99),
        ],
    ):
        with pytest.raises(WorkflowFailureError):
            await workflow_env.client.execute_workflow(
                SentimentAnalysisWorkflow.run,
                product_config,
                id=unique_workflow_id("store-final"),
                task_queue=TASK_QUEUE,
            )


async def test_query_handler_progress(workflow_env, product_config):
    """get_progress() returns a valid WorkflowProgress at any point during execution."""
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            make_scrape_activity(0),
            make_sentiment_activity(0),
            make_store_activity(0),
        ],
    ):
        handle = await workflow_env.client.start_workflow(
            SentimentAnalysisWorkflow.run,
            product_config,
            id=unique_workflow_id("query-progress"),
            task_queue=TASK_QUEUE,
        )
        progress = await handle.query(SentimentAnalysisWorkflow.get_progress)
        assert isinstance(progress, WorkflowProgress)
        assert progress.stage in {"starting", "scraping", "analyzing", "storing", "done"}
        assert progress.reviews_scraped >= 0
        assert progress.reviews_analyzed >= 0
        await handle.result()


def test_dataclass_validation():
    """__post_init__ guards reject invalid field values before they enter the workflow."""
    with pytest.raises(ValueError, match="max_reviews"):
        ProductConfig(product_name="X", product_id="Y", source_url="Z", max_reviews=0)

    with pytest.raises(ValueError, match="product_id"):
        ProductConfig(product_name="X", product_id="", source_url="Z", max_reviews=1)

    with pytest.raises(ValueError, match="rating"):
        Review(review_id="r1", product_id="P1", reviewer="A", rating=0,
               title="T", text="X", date="2025-01-01", source="test")

    with pytest.raises(ValueError, match="rating"):
        Review(review_id="r1", product_id="P1", reviewer="A", rating=6,
               title="T", text="X", date="2025-01-01", source="test")

    # Boundary values should not raise
    ProductConfig(product_name="X", product_id="Y", source_url="Z", max_reviews=1)
    Review(review_id="r1", product_id="P1", reviewer="A", rating=1,
           title="T", text="X", date="2025-01-01", source="test")
    Review(review_id="r1", product_id="P1", reviewer="A", rating=5,
           title="T", text="X", date="2025-01-01", source="test")


async def test_invalid_scraper_type(workflow_env):
    """An unknown scraper_type raises a non-retryable ApplicationError — workflow fails immediately."""
    config = ProductConfig(
        product_name="Test Product",
        product_id="TEST-INVALID",
        source_url="https://example.com",
        max_reviews=3,
        scraper_type="nonexistent_scraper",
    )
    async with Worker(
        workflow_env.client,
        task_queue=TASK_QUEUE,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            scrape_reviews_activity,  # real activity so ApplicationError path is exercised
            make_sentiment_activity(0),
            make_store_activity(0),
        ],
    ):
        with pytest.raises(WorkflowFailureError) as exc_info:
            await workflow_env.client.execute_workflow(
                SentimentAnalysisWorkflow.run,
                config,
                id=unique_workflow_id("invalid-scraper"),
                task_queue=TASK_QUEUE,
            )
        # Non-retryable ApplicationError propagates through the workflow failure chain:
        # WorkflowFailureError → ActivityError → ApplicationError
        activity_err = exc_info.value.cause
        assert isinstance(activity_err, ActivityError)
        app_err = activity_err.cause
        assert isinstance(app_err, ApplicationError)
        assert "nonexistent_scraper" in str(app_err)


async def test_store_activity_idempotency(tmp_path):
    """store_results_activity returns the existing DB row on retry without inserting a duplicate."""
    from activities.store_results import store_results_activity
    from db.init_db import init_db

    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    scores = [SentimentScore(review_id="r1", compound=0.5, positive=0.5, negative=0.0, neutral=0.5)]
    reviews_list = [Review(review_id="r1", product_id="P1", reviewer="Alice", rating=4,
                           title="Good", text="Works well", date="2025-01-01", source="test")]
    result = AverageResult(
        product_id="P1",
        product_name="Product 1",
        avg_compound=0.5,
        review_count=1,
        breakdown=SentimentBreakdown(positive_count=1, negative_count=0, neutral_count=0),
        scores=scores,
        reviews=reviews_list,
    )

    mock_info = MagicMock()
    mock_info.workflow_run_id = "test-wf-run-idempotency"

    with patch("activities.store_results.DB_PATH", db_path), \
         patch("activities.store_results.activity.info", return_value=mock_info):
        result1 = await store_results_activity(result)
        assert result1.run_id == "1"

        # Simulate a retry: Temporal re-sends the original input (run_id=None)
        result.run_id = None
        result2 = await store_results_activity(result)
        assert result2.run_id == "1"  # same row, not a new insert

    row_count = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM analysis_runs"
    ).fetchone()[0]
    assert row_count == 1
