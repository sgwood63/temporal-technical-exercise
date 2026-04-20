import os
import uuid

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from temporalio.client import Client, TLSConfig
from temporalio.testing import WorkflowEnvironment

from models.data_models import ProductConfig

# Separate task queue keeps test tasks away from any production worker.
# Workflow IDs are prefixed with "test-" so they're easy to filter in the
# Temporal Cloud UI: WorkflowId STARTS_WITH "test-"
TASK_QUEUE = "test-sentiment-tq"


def pytest_addoption(parser):
    parser.addoption(
        "--temporal-cloud",
        action="store_true",
        default=False,
        help="Run tests against Temporal Cloud using credentials from .env",
    )


def unique_workflow_id(prefix: str) -> str:
    return f"test-{prefix}-{uuid.uuid4().hex[:8]}"


class _CloudEnv:
    """Thin wrapper so workflow_env.client works whether backed by local or cloud."""
    def __init__(self, client: Client) -> None:
        self.client = client


async def _connect_cloud() -> Client:
    load_dotenv(override=True)
    address = os.environ["TEMPORAL_ADDRESS"]
    return await Client.connect(
        address,
        namespace=os.environ["TEMPORAL_NAMESPACE"],
        tls=TLSConfig(domain=address.split(":")[0]),
        api_key=os.environ["TEMPORAL_API_KEY"],
    )


@pytest_asyncio.fixture
async def workflow_env(request):
    if request.config.getoption("--temporal-cloud"):
        client = await _connect_cloud()
        yield _CloudEnv(client)
    else:
        async with await WorkflowEnvironment.start_time_skipping() as env:
            yield env


@pytest.fixture
def product_config():
    return ProductConfig(
        product_name="Test Headphones",
        product_id="TEST-001",
        source_url="https://example.com/product/TEST-001",
        max_reviews=3,
        scraper_type="mock",
    )
