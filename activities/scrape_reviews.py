from datetime import timedelta

from temporalio import activity

from models.data_models import ProductConfig, Review
from scrapers.registry import get_scraper


@activity.defn
async def scrape_reviews_activity(config: ProductConfig) -> list[Review]:
    """Fetch reviews for a product using the configured scraper plugin.

    Heartbeats on every page so Temporal can detect worker crashes quickly.
    Heartbeat state (page number) is stored in the heartbeat details — if the
    activity is retried on a new worker, it could resume from the last page
    (the mock scraper is seeded so re-fetching earlier pages is safe either way).
    """
    scraper = get_scraper(config.scraper_type)

    def heartbeat_fn(state: dict) -> None:
        activity.heartbeat(state)

    return await scraper.scrape(config, heartbeat_fn)
