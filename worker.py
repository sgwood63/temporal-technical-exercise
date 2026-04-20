"""Worker process — polls Temporal Cloud for workflow and activity tasks.

Run this in one terminal before starting any workflows:
    python worker.py
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from temporalio.client import Client, TLSConfig
from temporalio.worker import Worker

from activities.analyze_sentiment import analyze_sentiment_activity
from activities.scrape_reviews import scrape_reviews_activity
from activities.store_results import store_results_activity
from db.init_db import init_db
from logging_config import configure_logging
from workflows.sentiment_workflow import SentimentAnalysisWorkflow

load_dotenv(override=True)
configure_logging(config_file=os.environ.get("LOG_CONFIG"))

logger = logging.getLogger(__name__)


async def main() -> None:
    # Ensure the SQLite schema exists before we start accepting work
    init_db()

    client = await Client.connect(
        os.environ["TEMPORAL_ADDRESS"],
        namespace=os.environ["TEMPORAL_NAMESPACE"],
        tls=TLSConfig(
            # tmprl.cloud requires TLS; domain is the hostname without the port
            domain=os.environ["TEMPORAL_ADDRESS"].split(":")[0],
        ),
        api_key=os.environ["TEMPORAL_API_KEY"],
    )

    task_queue = os.environ["TASK_QUEUE"]

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[SentimentAnalysisWorkflow],
        activities=[
            scrape_reviews_activity,
            analyze_sentiment_activity,
            store_results_activity,
        ],
    )

    logger.info("Worker started — namespace=%s queue=%s", os.environ["TEMPORAL_NAMESPACE"], task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
