import logging
import sqlite3
from datetime import datetime, timezone

from temporalio import activity

from db.init_db import DB_PATH
from models.data_models import AverageResult

logger = logging.getLogger(__name__)


@activity.defn
async def store_results_activity(result: AverageResult) -> AverageResult:
    """Persist the completed analysis run to SQLite.

    Returns the input AverageResult with run_id populated from the DB
    autoincrement, so the workflow can surface the DB record ID to callers.

    Uses workflow_run_id as an idempotency key: if this activity is retried
    after a successful commit (e.g., worker crash before Temporal recorded the
    completion), the existing row is returned without a duplicate insert.
    """
    workflow_run_id = activity.info().workflow_run_id

    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        # Idempotency check: return existing result if already committed
        cursor.execute(
            "SELECT id FROM analysis_runs WHERE workflow_run_id = ?",
            (workflow_run_id,),
        )
        existing = cursor.fetchone()
        if existing:
            result.run_id = str(existing[0])
            return result

        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            """INSERT INTO analysis_runs
               (product_id, product_name, run_at, review_count, avg_score, status, source, workflow_run_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (result.product_id, result.product_name, now,
             result.review_count, result.avg_compound, "completed", result.source, workflow_run_id),
        )
        run_id = cursor.lastrowid

        for i, review in enumerate(result.reviews):
            cursor.execute(
                """INSERT INTO reviews
                   (run_id, review_id, reviewer, rating, title, text, date, source, verified)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, review.review_id, review.reviewer, review.rating,
                 review.title, review.text, review.date, review.source,
                 int(review.verified_purchase)),
            )
            if i % 50 == 49:
                activity.heartbeat({"reviews_inserted": i + 1})

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
        logger.info("Stored results — product=%s run_id=%d reviews=%d avg_compound=%+.4f",
                    result.product_name, run_id, result.review_count, result.avg_compound)
        return result
    finally:
        conn.close()
