from typing import Callable, Protocol, runtime_checkable
from models.data_models import ProductConfig, Review


@runtime_checkable
class ReviewScraper(Protocol):
    """Interface all review scrapers must implement.

    The activity passes heartbeat_fn so each scraper can signal liveness to
    Temporal without depending on the activity module directly.
    """

    @property
    def source_name(self) -> str:
        ...

    async def scrape(
        self,
        config: ProductConfig,
        heartbeat_fn: Callable[[dict], None],
    ) -> list[Review]:
        ...
