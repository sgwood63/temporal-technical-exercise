import logging
from datetime import timedelta

from temporalio import activity

from models.data_models import ProductConfig, Review
from scrapers.registry import get_scraper

logger = logging.getLogger(__name__)


@activity.defn
async def scrape_reviews_activity(config: ProductConfig) -> list[Review]:
    """Fetch reviews for a product using the configured scraper plugin.

    Heartbeats on every page so Temporal can detect worker crashes quickly.
    Heartbeat state (page number) is stored in the heartbeat details — if the
    activity is retried on a new worker, it could resume from the last page
    (the mock scraper is seeded so re-fetching earlier pages is safe either way).
    """
    logger.info("Scraping reviews — product_id=%s scraper=%s max=%d",
                config.product_id, config.scraper_type, config.max_reviews)

    scraper = get_scraper(config.scraper_type)

    def heartbeat_fn(state: dict) -> None:
        logger.debug("Heartbeat — page=%s", state.get("page"))
        activity.heartbeat(state)

    reviews = await scraper.scrape(config, heartbeat_fn)
    logger.info("Scrape complete — product_id=%s reviews=%d", config.product_id, len(reviews))
    return reviews
