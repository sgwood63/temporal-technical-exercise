from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProductConfig:
    product_name: str
    product_id: str
    source_url: str
    max_reviews: int = 15
    scraper_type: str = "mock"

    def __post_init__(self) -> None:
        if self.max_reviews < 1:
            raise ValueError(f"max_reviews must be >= 1, got {self.max_reviews}")
        if not self.product_id:
            raise ValueError("product_id must not be empty")


@dataclass
class Review:
    review_id: str
    product_id: str
    reviewer: str
    rating: int          # 1–5
    title: str
    text: str
    date: str            # ISO date string e.g. "2024-11-15"
    source: str          # e.g. "amazon_mock" or "amazon"
    verified_purchase: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.rating <= 5:
            raise ValueError(f"rating must be 1–5, got {self.rating}")


@dataclass
class SentimentScore:
    review_id: str
    compound: float      # -1.0 (most negative) to +1.0 (most positive) — primary metric
    positive: float
    negative: float
    neutral: float


@dataclass
class SentimentBreakdown:
    positive_count: int  # compound > 0.05
    negative_count: int  # compound < -0.05
    neutral_count: int   # -0.05 <= compound <= 0.05


@dataclass
class AverageResult:
    product_id: str
    product_name: str
    avg_compound: float
    review_count: int
    breakdown: SentimentBreakdown
    scores: list[SentimentScore] = field(default_factory=list)
    reviews: list["Review"] = field(default_factory=list)
    source: str = ""
    run_id: Optional[str] = None  # populated by store_results_activity after DB insert


@dataclass
class WorkflowProgress:
    stage: str           # "starting" | "scraping" | "analyzing" | "storing" | "done" | "failed"
    reviews_scraped: int
    reviews_analyzed: int
    message: str
