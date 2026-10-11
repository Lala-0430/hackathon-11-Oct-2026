"""SQLite storage for assessments.

Only derived features, question answers, and results are stored.
The raw password (and any hash of it) is NEVER stored.
"""

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.analyzer import SCORING_VERSION, Assessment

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    scoring_version TEXT    NOT NULL,
    length          INTEGER NOT NULL,
    has_lower       INTEGER NOT NULL,
    has_upper       INTEGER NOT NULL,
    has_digit       INTEGER NOT NULL,
    has_symbol      INTEGER NOT NULL,
    has_other       INTEGER NOT NULL,
    pool_size       INTEGER NOT NULL,
    entropy_bits    REAL    NOT NULL,
    patterns        TEXT    NOT NULL,  -- JSON array of detected pattern ids
    answers         TEXT    NOT NULL,  -- JSON object {question_id: bool}
    score           INTEGER NOT NULL,
    label           TEXT    NOT NULL,
    user_feedback   TEXT               -- 'accurate' | 'too_high' | 'too_low'
);
"""

FEEDBACK_VALUES = {"accurate", "too_high", "too_low"}


def db_path() -> str:
    return os.environ.get("DATABASE_PATH", "data/assessments.db")


@contextmanager
def connect():
    path = db_path()
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def save_assessment(assessment: Assessment, answers: dict[str, bool]) -> int:
    f = assessment.features
    with connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO assessments (
                created_at, scoring_version, length, has_lower, has_upper,
                has_digit, has_symbol, has_other, pool_size, entropy_bits,
                patterns, answers, score, label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                SCORING_VERSION,
                f.length, f.has_lower, f.has_upper, f.has_digit, f.has_symbol,
                f.has_other, f.pool_size, f.entropy_bits,
                json.dumps(f.patterns), json.dumps(answers),
                assessment.score, assessment.label,
            ),
        )
        return cur.lastrowid


def get_assessment(assessment_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM assessments WHERE id = ?", (assessment_id,)
        ).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["patterns"] = json.loads(record["patterns"])
    record["answers"] = json.loads(record["answers"])
    return record


def set_feedback(assessment_id: int, feedback: str) -> bool:
    with connect() as conn:
        cur = conn.execute(
            "UPDATE assessments SET user_feedback = ? WHERE id = ?",
            (feedback, assessment_id),
        )
        return cur.rowcount > 0


def get_stats() -> dict:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM assessments").fetchone()[0]
        by_label = conn.execute(
            "SELECT label, COUNT(*) AS n FROM assessments GROUP BY label"
        ).fetchall()
        by_feedback = conn.execute(
            "SELECT user_feedback, COUNT(*) AS n FROM assessments "
            "WHERE user_feedback IS NOT NULL GROUP BY user_feedback"
        ).fetchall()
    return {
        "total_assessments": total,
        "by_label": {r["label"]: r["n"] for r in by_label},
        "by_feedback": {r["user_feedback"]: r["n"] for r in by_feedback},
    }
