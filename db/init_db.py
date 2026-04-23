import sqlite3
import os

DB_PATH = os.environ.get("DB_PATH", "sentiment_results.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id       TEXT    NOT NULL,
    product_name     TEXT    NOT NULL,
    run_at           TEXT    NOT NULL,
    review_count     INTEGER NOT NULL,
    avg_score        REAL    NOT NULL,
    status           TEXT    NOT NULL,
    source           TEXT    NOT NULL,
    workflow_run_id  TEXT
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

CREATE INDEX IF NOT EXISTS idx_reviews_run_id ON reviews(run_id);
CREATE INDEX IF NOT EXISTS idx_sentiment_run_id ON sentiment_scores(run_id);
-- Partial unique index: only enforce uniqueness when workflow_run_id is present,
-- so existing rows with NULL are unaffected after schema migrations.
CREATE UNIQUE INDEX IF NOT EXISTS idx_analysis_runs_workflow_run_id
    ON analysis_runs(workflow_run_id) WHERE workflow_run_id IS NOT NULL;
"""

# Migrate existing DBs: add workflow_run_id column if it was created before this column existed.
_MIGRATION = """
ALTER TABLE analysis_runs ADD COLUMN workflow_run_id TEXT;
"""


def init_db(db_path: str = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(_MIGRATION)
    except sqlite3.OperationalError:
        pass  # column already exists
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
