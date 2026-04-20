import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from models.data_models import (
    AverageResult,
    ProductConfig,
    Review,
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
