import logging

from temporalio import activity
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from models.data_models import Review, SentimentScore

# Load the VADER lexicon once at module import time — it's a ~300 KB file.
# All activity invocations in this worker process share this instance.
_analyzer = SentimentIntensityAnalyzer()

logger = logging.getLogger(__name__)


@activity.defn
async def analyze_sentiment_activity(review: Review) -> SentimentScore:
    """Run VADER sentiment analysis on a single review.

    Combines title + body for richer signal — short titles like "Terrible!"
    carry strong sentiment that would be diluted if only the body were scored.
    """
    full_text = f"{review.title}. {review.text}"
    scores = _analyzer.polarity_scores(full_text)
    score = SentimentScore(
        review_id=review.review_id,
        compound=scores["compound"],
        positive=scores["pos"],
        negative=scores["neg"],
        neutral=scores["neu"],
    )
    logger.debug("Sentiment — review_id=%s compound=%+.4f", review.review_id, score.compound)
    activity.heartbeat({"review_id": review.review_id})
    return score
