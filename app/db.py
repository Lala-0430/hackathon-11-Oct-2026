"""Storage for assessments: SQLite locally, PostgreSQL in production.

Set DATABASE_URL (e.g. a Neon connection string) to use PostgreSQL.
Otherwise a SQLite file at DATABASE_PATH is used.

Only derived features, question answers, and results are stored.
The raw password (and any hash of it) is NEVER stored.
"""

import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.analyzer import SCORING_VERSION, Assessment

SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments (
    id              {id_column},
    public_id       TEXT    NOT NULL UNIQUE,  -- random id exposed by the API
    created_at      TEXT    NOT NULL,
    scoring_version TEXT    NOT NULL,
    length          INTEGER NOT NULL,
    has_lower       INTEGER NOT NULL,
    has_upper       INTEGER NOT NULL,
    has_digit       INTEGER NOT NULL,
    has_symbol      INTEGER NOT NULL,
    has_other       INTEGER NOT NULL,
    pool_size       INTEGER NOT NULL,
    entropy_bits    {float_type} NOT NULL,
    patterns        TEXT    NOT NULL,  -- JSON array of detected pattern ids
    answers         TEXT    NOT NULL,  -- JSON object {{question_id: bool}}
    score           INTEGER NOT NULL,
    label           TEXT    NOT NULL,
    user_feedback   TEXT               -- 'accurate' | 'too_high' | 'too_low'
)
"""

SQLITE_TYPES = {"id_column": "INTEGER PRIMARY KEY AUTOINCREMENT", "float_type": "REAL"}
POSTGRES_TYPES = {"id_column": "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
                  "float_type": "DOUBLE PRECISION"}

FEEDBACK_VALUES = {"accurate", "too_high", "too_low"}


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "")


def is_postgres() -> bool:
    return database_url().startswith(("postgres://", "postgresql://"))


def db_path() -> str:
    return os.environ.get("DATABASE_PATH", "data/assessments.db")


class _Conn:
    """Thin wrapper so the same SQL (with `?` placeholders) runs on both backends."""

    def __init__(self, raw, postgres: bool):
        self.raw = raw
        self.postgres = postgres

    def execute(self, sql: str, params: tuple = ()):
        if self.postgres:
            sql = sql.replace("?", "%s")
        return self.raw.execute(sql, params)


@contextmanager
def connect():
    if is_postgres():
        import psycopg
        from psycopg.rows import dict_row

        raw = psycopg.connect(database_url(), row_factory=dict_row)
    else:
        path = db_path()
        if path != ":memory:":
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        raw = sqlite3.connect(path)
        raw.row_factory = sqlite3.Row
    try:
        yield _Conn(raw, is_postgres())
        raw.commit()
    finally:
        raw.close()


def _migrate_sqlite(conn: _Conn) -> None:
    """Add public_id to SQLite databases created before it existed."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(assessments)")}
    if "public_id" in columns:
        return
    conn.execute("ALTER TABLE assessments ADD COLUMN public_id TEXT")
    for row in conn.execute("SELECT id FROM assessments").fetchall():
        conn.execute("UPDATE assessments SET public_id = ? WHERE id = ?",
                     (secrets.token_hex(16), row["id"]))
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_public_id ON assessments(public_id)")


def init_db() -> None:
    with connect() as conn:
        types = POSTGRES_TYPES if conn.postgres else SQLITE_TYPES
        conn.execute(SCHEMA.format(**types))
        if not conn.postgres:
            _migrate_sqlite(conn)


def save_assessment(assessment: Assessment, answers: dict[str, bool]) -> str:
    """Store an assessment and return its public id."""
    f = assessment.features
    public_id = secrets.token_hex(16)
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO assessments (
                public_id, created_at, scoring_version, length, has_lower,
                has_upper, has_digit, has_symbol, has_other, pool_size,
                entropy_bits, patterns, answers, score, label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                public_id,
                datetime.now(timezone.utc).isoformat(),
                SCORING_VERSION,
                f.length, int(f.has_lower), int(f.has_upper), int(f.has_digit),
                int(f.has_symbol), int(f.has_other), f.pool_size, f.entropy_bits,
                json.dumps(f.patterns), json.dumps(answers),
                assessment.score, assessment.label,
            ),
        )
    return public_id


def get_assessment(public_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM assessments WHERE public_id = ?", (public_id,)
        ).fetchone()
    if row is None:
        return None
    record = dict(row)
    record["patterns"] = json.loads(record["patterns"])
    record["answers"] = json.loads(record["answers"])
    return record


def set_feedback(public_id: str, feedback: str) -> bool:
    """Record feedback once. Returns False if not found or already given."""
    with connect() as conn:
        cur = conn.execute(
            "UPDATE assessments SET user_feedback = ? "
            "WHERE public_id = ? AND user_feedback IS NULL",
            (feedback, public_id),
        )
        return cur.rowcount > 0


def get_stats() -> dict:
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM assessments").fetchone()["n"]
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
