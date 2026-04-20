"""Worker process — polls Temporal Cloud for workflow and activity tasks.

Run this in one terminal before starting any workflows:
    python worker.py
"""

import asyncio
import os

from dotenv import load_dotenv
from temporalio.client import Client, TLSConfig
from temporalio.worker import Worker

from activities.analyze_sentiment import analyze_sentiment_activity
from activities.scrape_reviews import scrape_reviews_activity
from activities.store_results import store_results_activity
from db.init_db import init_db
from workflows.sentiment_workflow import SentimentAnalysisWorkflow

load_dotenv()


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

    print(f"Worker started. Namespace: {os.environ['TEMPORAL_NAMESPACE']}  Queue: {task_queue}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
