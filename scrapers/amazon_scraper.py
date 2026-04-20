"""Real Amazon scraper stub.

This module shows exactly where a Playwright-based implementation would live
and what it would need to do. It raises NotImplementedError so the interface
is exercisable without pulling in the playwright dependency.

To implement for real:
  pip install playwright
  playwright install chromium

Key Amazon review page structure (as of 2025):
  - URL pattern:  https://www.amazon.com/product-reviews/<ASIN>?pageNumber=<N>
  - Review cards: div[data-hook="review"]
  - Star rating:  i[data-hook="review-star-rating"] span.a-icon-alt  → "4.0 out of 5 stars"
  - Title:        span[data-hook="review-title"] span:last-child
  - Body:         span[data-hook="review-body"] span
  - Reviewer:     span.a-profile-name
  - Date:         span[data-hook="review-date"]       → "Reviewed in the United States on November 15, 2024"
  - Verified:     span[data-hook="avp-badge"]         → presence indicates verified purchase
"""

from typing import Callable

from models.data_models import ProductConfig, Review


class AmazonScraper:
    """Playwright-based Amazon review scraper (stub — not yet implemented)."""

    @property
    def source_name(self) -> str:
        return "amazon"

    async def scrape(
        self,
        config: ProductConfig,
        heartbeat_fn: Callable[[dict], None],
    ) -> list[Review]:
        # Real implementation outline:
        #
        #   async with async_playwright() as pw:
        #       browser = await pw.chromium.launch(headless=True)
        #       page = await browser.new_page()
        #       reviews = []
        #       page_num = 1
        #
        #       while len(reviews) < config.max_reviews:
        #           heartbeat_fn({"page": page_num})
        #           url = f"https://www.amazon.com/product-reviews/{config.product_id}?pageNumber={page_num}"
        #           await page.goto(url)
        #           cards = await page.query_selector_all('div[data-hook="review"]')
        #           if not cards:
        #               break
        #           for card in cards:
        #               reviews.append(await _parse_card(card, config.product_id, self.source_name))
        #           page_num += 1
        #
        #       await browser.close()
        #       return reviews[:config.max_reviews]

        raise NotImplementedError(
            "AmazonScraper is a stub. Use scraper_type='mock' for the demo, "
            "or implement the Playwright logic in this method."
        )
