"""
app.core.telemetry
~~~~~~~~~~~~~~~~~~

Lightweight, append-only pipeline instrumentation layer.

Design principles
-----------------
* **Zero coupling to existing tables** – a single new `pipeline_events` table
  holds all telemetry.  No existing DDL or query is touched.
* **Fire-and-forget** – callers wrap a pipeline stage with `record_stage()`.
  All writes go through the same `db.execute` path that the rest of the app
  already uses, so locking and Postgres compatibility come for free.
* **No secrets in storage** – only sanitised stage names, durations, verdicts,
  and truncated error messages are persisted.  Full URLs, transcripts, claims,
  and API keys are never stored here.
* **Graceful degradation** – every write is wrapped in try/except so a telemetry
  failure can never crash the verification pipeline.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from typing import Generator

from app.core import db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema extension — added to COLUMN_MIGRATIONS in db.py is not appropriate
# here because this is a full new table, not a column addition.  We bootstrap
# it lazily on first use so no startup ordering changes are needed.
# ---------------------------------------------------------------------------
_TELEMETRY_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS pipeline_events (
    id          TEXT    PRIMARY KEY,
    check_id    TEXT    NOT NULL,
    stage       TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'ok',
    duration_ms INTEGER,
    error_msg   TEXT,
    recorded_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_TELEMETRY_IDX1_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_pe_check_id ON pipeline_events (check_id)"
)
_TELEMETRY_IDX2_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_pe_stage ON pipeline_events (stage)"
)
_TELEMETRY_IDX3_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_pe_recorded ON pipeline_events (recorded_at)"
)

_bootstrapped = False


def _ensure_schema() -> None:
    global _bootstrapped
    if _bootstrapped:
        return
    try:
        db.execute(_TELEMETRY_TABLE_DDL)
        db.execute(_TELEMETRY_IDX1_DDL)
        db.execute(_TELEMETRY_IDX2_DDL)
        db.execute(_TELEMETRY_IDX3_DDL)
        _bootstrapped = True
    except Exception:
        logger.exception("telemetry: failed to create pipeline_events table")


def record_event(
    check_id: str,
    stage: str,
    status: str = "ok",
    duration_ms: int | None = None,
    error_msg: str | None = None,
) -> None:
    """Persist a single pipeline event.  Never raises — any storage failure is
    logged and swallowed so the caller's pipeline is unaffected."""
    _ensure_schema()
    # Truncate error messages to 512 chars — enough to identify the failure
    # class without risking leaking sensitive content from an exception string.
    if error_msg:
        error_msg = error_msg[:512]
    event_id = str(uuid.uuid4())
    try:
        db.execute(
            "INSERT INTO pipeline_events "
            "(id, check_id, stage, status, duration_ms, error_msg) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, check_id, stage, status, duration_ms, error_msg),
        )
    except Exception:
        logger.exception(
            "telemetry: failed to write event check_id=%s stage=%s", check_id, stage
        )


@contextmanager
def record_stage(check_id: str, stage: str) -> Generator[None, None, None]:
    """Context manager that records start/end timing for a pipeline stage.

    Usage::

        with record_stage(check_id, "downloading"):
            video_path = download_clip(url, check_dir)

    On success writes status='ok' with elapsed milliseconds.
    On exception writes status='error' with truncated message, then re-raises.
    """
    t0 = time.monotonic()
    try:
        yield
    except Exception as exc:
        elapsed = int((time.monotonic() - t0) * 1000)
        # Use only the exception *type* name, not str(exc), to avoid storing
        # potentially sensitive URLs or claim text from the traceback.
        record_event(
            check_id,
            stage,
            status="error",
            duration_ms=elapsed,
            error_msg=type(exc).__name__,
        )
        raise
    else:
        elapsed = int((time.monotonic() - t0) * 1000)
        record_event(check_id, stage, status="ok", duration_ms=elapsed)
