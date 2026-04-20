import sqlite3
from datetime import datetime, timezone

from temporalio import activity

from db.init_db import DB_PATH
from models.data_models import AverageResult


@activity.defn
async def store_results_activity(result: AverageResult) -> AverageResult:
    """Persist the completed analysis run to SQLite.

    Returns the input AverageResult with run_id populated from the DB
    autoincrement, so the workflow can surface the DB record ID to callers.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """INSERT INTO analysis_runs
               (product_id, product_name, run_at, review_count, avg_score, status, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (result.product_id, result.product_name, now,
             result.review_count, result.avg_compound, "completed", result.source),
        )
        run_id = cursor.lastrowid

        for review in result.reviews:
            cursor.execute(
                """INSERT INTO reviews
                   (run_id, review_id, reviewer, rating, title, text, date, source, verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, review.review_id, review.reviewer, review.rating,
                 review.title, review.text, review.date, review.source,
                 int(review.verified_purchase)),
            )

        for score in result.scores:
            cursor.execute(
                """INSERT INTO sentiment_scores
                   (review_id, run_id, compound, positive, negative, neutral)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (score.review_id, run_id,
                 score.compound, score.positive, score.negative, score.neutral),
            )

        conn.commit()
        result.run_id = str(run_id)
        return result
    finally:
        conn.close()
