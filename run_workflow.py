"""Workflow starter — kick off a sentiment analysis run or query a running one.

Usage:
    # Start a workflow and wait for the result
    python run_workflow.py

    # Override product or review count
    python run_workflow.py --product-name "Kindle Paperwhite" --product-id B09SWRYPB9 --max-reviews 20

    # Query the live progress of a running workflow
    python run_workflow.py --query-only sentiment-sony-wh1000xm5-abc12345

    # Use the real Amazon scraper (requires implementing AmazonScraper)
    python run_workflow.py --scraper amazon
"""

import argparse
import asyncio
import os
import uuid

from dotenv import load_dotenv
from temporalio.client import Client, TLSConfig

from models.data_models import ProductConfig
from workflows.sentiment_workflow import SentimentAnalysisWorkflow

load_dotenv(override=True)

_DEFAULT = ProductConfig(
    product_name="Sony WH-1000XM5 Headphones",
    product_id="B09XS7JWHH",
    source_url="https://www.amazon.com/dp/B09XS7JWHH",
    max_reviews=15,
    scraper_type="mock",
)


async def _connect() -> Client:
    return await Client.connect(
        os.environ["TEMPORAL_ADDRESS"],
        namespace=os.environ["TEMPORAL_NAMESPACE"],
        tls=TLSConfig(domain=os.environ["TEMPORAL_ADDRESS"].split(":")[0]),
        api_key=os.environ["TEMPORAL_API_KEY"],
    )


async def query_workflow(workflow_id: str) -> None:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id)
    progress = await handle.query(SentimentAnalysisWorkflow.get_progress)
    print(f"Workflow : {workflow_id}")
    print(f"Stage    : {progress.stage}")
    print(f"Scraped  : {progress.reviews_scraped}")
    print(f"Analyzed : {progress.reviews_analyzed}")
    print(f"Message  : {progress.message}")


async def run_workflow(config: ProductConfig) -> None:
    client = await _connect()

    workflow_id = f"sentiment-{config.product_id}-{uuid.uuid4().hex[:8]}"

    print(f"Starting workflow : {workflow_id}")
    print(f"Product           : {config.product_name} ({config.product_id})")
    print(f"Scraper           : {config.scraper_type}")
    print(f"Max reviews       : {config.max_reviews}")
    print()

    handle = await client.start_workflow(
        SentimentAnalysisWorkflow.run,
        config,
        id=workflow_id,
        task_queue=os.environ["TASK_QUEUE"],
    )

    print(f"Workflow started. RunID: {handle.result_run_id}")
    print("Waiting for result... (Ctrl-C to detach; re-query with --query-only)")
    print()

    result = await handle.result()

    print("═" * 50)
    print(f"  Product   : {result.product_name}")
    print(f"  Reviews   : {result.review_count}")
    print(f"  Avg score : {result.avg_compound:+.4f}  (-1 = most negative, +1 = most positive)")
    print(f"  Positive  : {result.breakdown.positive_count}")
    print(f"  Neutral   : {result.breakdown.neutral_count}")
    print(f"  Negative  : {result.breakdown.negative_count}")
    print(f"  DB run ID : {result.run_id}")
    print("═" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run or query a sentiment analysis workflow")
    parser.add_argument("--product-name", default=_DEFAULT.product_name)
    parser.add_argument("--product-id", default=_DEFAULT.product_id)
    parser.add_argument("--source-url", default=_DEFAULT.source_url)
    parser.add_argument("--max-reviews", type=int, default=_DEFAULT.max_reviews)
    parser.add_argument("--scraper", default=_DEFAULT.scraper_type,
                        choices=["mock", "amazon"],
                        help="Scraper plugin to use (default: mock)")
    parser.add_argument("--query-only", metavar="WORKFLOW_ID",
                        help="Query the live progress of an already-running workflow")
    args = parser.parse_args()

    if args.query_only:
        asyncio.run(query_workflow(args.query_only))
    else:
        config = ProductConfig(
            product_name=args.product_name,
            product_id=args.product_id,
            source_url=args.source_url,
            max_reviews=args.max_reviews,
            scraper_type=args.scraper,
        )
        asyncio.run(run_workflow(config))


if __name__ == "__main__":
    main()
