"""
SQLite persistence for incidents.

Kept as plain sqlite3 (no ORM) to stay dependency-light, matching the
project's "single machine, single operator" scope.

Schema is versioned via safe ALTER TABLE migrations so the file survives
upgrades without needing a drop/recreate.
"""
import sqlite3
import threading
from contextlib import contextmanager

from . import config

_local = threading.local()


def _connect():
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate(conn):
    """Add columns introduced in later versions — safe to run on every startup."""
    migrations = [
        "ALTER TABLE incidents ADD COLUMN gps_lat REAL",
        "ALTER TABLE incidents ADD COLUMN gps_lon REAL",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            # Column already exists — not an error
            pass


def init_db():
    import os
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at    TEXT    NOT NULL,
                camera_id     TEXT    NOT NULL,
                confidence    REAL    NOT NULL,
                snapshot_path TEXT    NOT NULL,
                status        TEXT    NOT NULL DEFAULT 'pending',
                    -- pending | confirmed | dismissed
                decided_at    TEXT,
                alert_sent    INTEGER,
                    -- NULL = n/a, 1 = success, 0 = failed
                alert_error   TEXT,
                gps_lat       REAL,
                gps_lon       REAL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);"
        )
        _migrate(conn)


def create_incident(
    created_at: str,
    camera_id: str,
    confidence: float,
    snapshot_path: str,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    status: str = 'confirmed' # Changed from hardcoded 'pending'
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO incidents
                (created_at, camera_id, confidence, snapshot_path, status, gps_lat, gps_lon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (created_at, camera_id, confidence, snapshot_path, status, gps_lat, gps_lon),
        )
        return cur.lastrowid


def get_pending():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE status = 'pending' ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_history(limit: int = 200):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM incidents WHERE status != 'pending' ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_incident(incident_id: int):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM incidents WHERE id = ?", (incident_id,)
        ).fetchone()
        return dict(row) if row else None


def decide_incident(
    incident_id: int,
    status: str,
    decided_at: str,
    alert_sent=None,
    alert_error=None,
):
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE incidents
            SET status = ?, decided_at = ?, alert_sent = ?, alert_error = ?
            WHERE id = ?
            """,
            (status, decided_at, alert_sent, alert_error, incident_id),
        )


def counts():
    with get_conn() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) c FROM incidents WHERE status='pending'"
        ).fetchone()["c"]
        confirmed = conn.execute(
            "SELECT COUNT(*) c FROM incidents WHERE status='confirmed'"
        ).fetchone()["c"]
        dismissed = conn.execute(
            "SELECT COUNT(*) c FROM incidents WHERE status='dismissed'"
        ).fetchone()["c"]
        return {"pending": pending, "confirmed": confirmed, "dismissed": dismissed}


def count_today() -> int:
    """Number of incidents created today (any status)."""
    with get_conn() as conn:
        today = __import__("datetime").date.today().isoformat()
        row = conn.execute(
            "SELECT COUNT(*) c FROM incidents WHERE created_at LIKE ?",
            (f"{today}%",),
        ).fetchone()
        return row["c"] if row else 0
