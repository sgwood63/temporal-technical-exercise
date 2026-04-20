import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "sentiment_results.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id   TEXT    NOT NULL,
    product_name TEXT    NOT NULL,
    run_at       TEXT    NOT NULL,
    review_count INTEGER NOT NULL,
    avg_score    REAL    NOT NULL,
    status       TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES analysis_runs(id),
    review_id   TEXT    NOT NULL,
    reviewer    TEXT    NOT NULL,
    rating      INTEGER NOT NULL,
    title       TEXT    NOT NULL,
    text        TEXT    NOT NULL,
    date        TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    verified    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sentiment_scores (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id TEXT    NOT NULL,
    run_id    INTEGER NOT NULL REFERENCES analysis_runs(id),
    compound  REAL    NOT NULL,
    positive  REAL    NOT NULL,
    negative  REAL    NOT NULL,
    neutral   REAL    NOT NULL
);
"""


def init_db(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
