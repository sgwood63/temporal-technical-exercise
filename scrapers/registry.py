from scrapers.base import ReviewScraper
from scrapers.mock_scraper import MockScraper
from scrapers.amazon_scraper import AmazonScraper

SCRAPERS: dict[str, type] = {
    "mock": MockScraper,
    "amazon": AmazonScraper,
}


def get_scraper(scraper_type: str) -> ReviewScraper:
    cls = SCRAPERS.get(scraper_type)
    if cls is None:
        available = ", ".join(SCRAPERS.keys())
        raise ValueError(f"Unknown scraper_type '{scraper_type}'. Available: {available}")
    return cls()
