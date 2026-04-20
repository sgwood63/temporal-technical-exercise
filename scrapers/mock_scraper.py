import asyncio
import random
from typing import Callable

from models.data_models import ProductConfig, Review

# Realistic Amazon review corpus spanning the full 1–5 star sentiment range.
# Each entry: (rating, title, body)
_REVIEW_TEMPLATES = [
    (5, "Absolutely love this!", "This product exceeded all my expectations. The build quality is superb and it arrived perfectly packaged. I've tried several similar products and nothing comes close. Highly recommend to anyone on the fence."),
    (5, "Best purchase this year", "Incredible quality for the price. It works exactly as described, setup was a breeze, and it looks great. I've already recommended it to three friends."),
    (5, "Outstanding — worth every penny", "I was skeptical given the price point but this completely changed my mind. It's been two months and it still performs flawlessly. Customer service was also responsive when I had a minor question."),
    (4, "Really good, minor quibbles", "Works great overall and the quality is solid. My only complaint is that the packaging could be improved and setup took longer than the instructions suggested. Would still buy again."),
    (4, "Happy with the purchase", "Does what it says on the tin. Shipping was fast, product matches the description, and it feels well-made. Docking one star because a small accessory was missing from the box."),
    (4, "Solid product, good value", "I've had this for a few weeks now and it's been reliable. The design is intuitive. Not quite perfect but definitely a solid purchase for the price."),
    (3, "It's okay", "Does what it says but nothing special. Average quality. I expected a bit more based on the reviews but it's serviceable. Might return it and look for something better."),
    (3, "Mixed feelings", "Some features are great, others disappoint. Performance is acceptable but I've seen better at this price. Not bad, not great — squarely in the middle."),
    (3, "Adequate but not impressive", "It arrived on time and works as described. I just feel underwhelmed. The material feels cheaper than photos suggest and the finish isn't as polished. Fine for casual use."),
    (2, "Not impressed", "Expected significantly better quality given the price and reviews. Several issues appeared after just one week of normal use. The design also feels somewhat flimsy."),
    (2, "Disappointing", "Had high hopes based on the product description but it didn't live up to them. Performance is inconsistent and it feels like a budget item dressed up in marketing. I wouldn't buy again."),
    (1, "Terrible experience", "Broke after two days of light use. This is a complete waste of money. The quality is nowhere near what's shown in the photos. Already filed for a return."),
    (1, "Awful product — do not buy", "Does not work as advertised. Multiple defects right out of the box. Very disappointed and frustrated with this purchase. Save your money and look elsewhere."),
    (1, "Fell apart immediately", "Received a product that was already damaged. The materials are cheap and the construction is poor. I cannot believe this has the ratings it does — misleading reviews at play here."),
    (2, "Would not recommend", "Returned after a week. Doesn't perform as described and customer support was unhelpful when I reached out. There are much better options at this price point."),
]

_REVIEWER_FIRST = ["James", "Maria", "David", "Sarah", "Robert", "Lisa", "Michael", "Jennifer", "Chris", "Amanda", "Daniel", "Jessica", "Matthew", "Ashley", "Andrew"]
_REVIEWER_LAST = ["S.", "T.", "M.", "R.", "K.", "L.", "B.", "W.", "H.", "C.", "P.", "G.", "N.", "F.", "D."]

_DATES = [
    "2024-08-03", "2024-09-17", "2024-10-05", "2024-10-22", "2024-11-01",
    "2024-11-15", "2024-12-03", "2024-12-19", "2025-01-07", "2025-01-28",
    "2025-02-14", "2025-02-28", "2025-03-10", "2025-03-25", "2025-04-02",
]


class MockScraper:
    """Returns deterministic mock Amazon reviews for any product.

    Using a seeded RNG keyed on product_id + page number ensures the same
    reviews are returned on every call for a given product. This makes the
    activity idempotent across retries — critical for Temporal correctness.
    """

    @property
    def source_name(self) -> str:
        return "amazon_mock"

    async def scrape(
        self,
        config: ProductConfig,
        heartbeat_fn: Callable[[dict], None],
    ) -> list[Review]:
        reviews: list[Review] = []
        reviews_per_page = 5
        total_pages = max(1, -(-config.max_reviews // reviews_per_page))  # ceiling div

        for page in range(1, total_pages + 1):
            heartbeat_fn({"page": page, "total_pages": total_pages})

            # Simulate network latency for fetching a review page
            await asyncio.sleep(1)

            page_reviews = self._generate_page(config, page, reviews_per_page)
            reviews.extend(page_reviews)

            if len(reviews) >= config.max_reviews:
                break

        return reviews[:config.max_reviews]

    def _generate_page(self, config: ProductConfig, page: int, per_page: int) -> list[Review]:
        rng = random.Random(f"{config.product_id}-page-{page}")
        templates = rng.choices(_REVIEW_TEMPLATES, k=per_page)
        result = []
        for i, (rating, title, text) in enumerate(templates):
            result.append(Review(
                review_id=f"{config.product_id}-p{page}-r{i}",
                product_id=config.product_id,
                reviewer=f"{rng.choice(_REVIEWER_FIRST)} {rng.choice(_REVIEWER_LAST)}",
                rating=rating,
                title=title,
                text=text,
                date=rng.choice(_DATES),
                source=self.source_name,
                verified_purchase=rng.random() > 0.15,
            ))
        return result
