"""
app.api.observability
~~~~~~~~~~~~~~~~~~~~~

Read-only API endpoints that expose aggregated telemetry for the Observability
Dashboard.  All endpoints are protected by the existing AuthMiddleware and
return only pre-aggregated, sanitised data — no raw URLs, transcripts, claims,
or error payloads that could contain sensitive content are surfaced.

Routes
------
GET /api/observability/summary          Overall counts, success rate, throughput
GET /api/observability/stage-stats      Per-stage avg/p95 duration + error rate
GET /api/observability/executions       Paginated execution history (reel_checks)
GET /api/observability/errors           Recent pipeline error events (sanitised)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query

from app.core import db
from app.core.telemetry import _ensure_schema

router = APIRouter(prefix="/api/observability", tags=["observability"])

# Canonical stage ordering used by the pipeline (for consistent UI display)
PIPELINE_STAGES = [
    "downloading",
    "transcribing",
    "extracting_claims",
    "verifying_claims",
    "concluding",
]


def _since_clause(hours: int) -> tuple[str, tuple]:
    """Return a WHERE fragment and params tuple for the time-range filter.

    Computes the cutoff timestamp in Python as a timezone-naive ISO-8601
    string (matching how SQLite's ``datetime('now')`` stores values) and
    passes it as a parameter.  The ``pe.`` table alias means this helper
    is only valid for queries against ``pipeline_events``."""
    if hours <= 0:
        return ("", ())
    from datetime import timedelta
    cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_str = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")
    return ("AND pe.recorded_at >= ?", (cutoff_str,))


@router.get("/summary")
def get_summary(hours: int = Query(default=24, ge=0, le=720)) -> dict[str, Any]:
    """High-level overview: total executions, completion rate, error count,
    and checks started in the given time window."""
    _ensure_schema()
    hours = int(hours)

    time_filter, time_params = _since_clause(hours)

    # Total reel checks and their terminal statuses
    checks_rows = db.fetch_all(
        f"SELECT status, COUNT(*) AS cnt FROM reel_checks "
        f"{'WHERE created_at >= ?' if hours > 0 else ''} GROUP BY status",
        time_params if hours > 0 else (),
    )
    status_counts: dict[str, int] = {}
    total = 0
    for row in checks_rows:
        d = dict(row)
        status_counts[d["status"]] = d["cnt"]
        total += d["cnt"]

    done = status_counts.get("done", 0)
    error = status_counts.get("error", 0)
    in_progress = total - done - error

    success_rate = round(done / total * 100, 1) if total > 0 else None

    # Pipeline-event-level totals for error rate
    event_rows = db.fetch_all(
        f"SELECT status, COUNT(*) AS cnt FROM pipeline_events pe "
        f"WHERE 1=1 {time_filter} GROUP BY status",
        time_params,
    )
    event_counts: dict[str, int] = {}
    for row in event_rows:
        d = dict(row)
        event_counts[d["status"]] = d["cnt"]
    total_events = sum(event_counts.values())
    error_events = event_counts.get("error", 0)
    pipeline_error_rate = (
        round(error_events / total_events * 100, 1) if total_events > 0 else None
    )

    # Avg duration of completed checks (completed_at - created_at in seconds)
    # We do this in Python to stay DB-agnostic.
    completed_rows = db.fetch_all(
        f"SELECT created_at, completed_at FROM reel_checks "
        f"WHERE status='done' AND completed_at IS NOT NULL "
        f"{'AND created_at >= ?' if hours > 0 else ''}",
        time_params if hours > 0 else (),
    )
    durations_s: list[float] = []
    for row in completed_rows:
        d = dict(row)
        try:
            t0 = datetime.fromisoformat(d["created_at"])
            t1 = datetime.fromisoformat(d["completed_at"])
            durations_s.append((t1 - t0).total_seconds())
        except Exception:
            pass
    avg_duration_s = (
        round(sum(durations_s) / len(durations_s), 1) if durations_s else None
    )

    return {
        "period_hours": hours,
        "total_checks": total,
        "done": done,
        "error": error,
        "in_progress": in_progress,
        "success_rate_pct": success_rate,
        "pipeline_error_rate_pct": pipeline_error_rate,
        "avg_check_duration_s": avg_duration_s,
        "total_pipeline_events": total_events,
    }


@router.get("/stage-stats")
def get_stage_stats(hours: int = Query(default=24, ge=0, le=720)) -> list[dict[str, Any]]:
    """Per-stage aggregated statistics: count, success/error split, average
    duration (ms), and p95 duration (ms).  Stages with no data return zeros.
    Events whose duration_ms is null are still counted in totals and error
    rate — only the avg/p95 computations exclude them."""
    _ensure_schema()
    hours = int(hours)
    time_filter, time_params = _since_clause(hours)

    rows = db.fetch_all(
        f"SELECT stage, status, duration_ms FROM pipeline_events pe "
        f"WHERE 1=1 {time_filter} ORDER BY stage, status",
        time_params,
    )

    from collections import defaultdict
    stage_data: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"ok_durations": [], "error_durations": [], "ok_count": 0, "error_count": 0}
    )
    for row in rows:
        d = dict(row)
        entry = stage_data[d["stage"]]
        if d["status"] == "ok":
            entry["ok_count"] += 1
            if d["duration_ms"] is not None:
                entry["ok_durations"].append(d["duration_ms"])
        else:
            entry["error_count"] += 1
            if d["duration_ms"] is not None:
                entry["error_durations"].append(d["duration_ms"])

    def _p95(vals: list[int]) -> int | None:
        if not vals:
            return None
        sorted_v = sorted(vals)
        idx = max(0, int(len(sorted_v) * 0.95) - 1)
        return sorted_v[idx]

    def _build_stage_row(stage: str, data: dict) -> dict[str, Any]:
        all_durations = data["ok_durations"] + data["error_durations"]
        total = data["ok_count"] + data["error_count"]
        return {
            "stage": stage,
            "total_events": total,
            "ok_count": data["ok_count"],
            "error_count": data["error_count"],
            "avg_duration_ms": (
                round(sum(all_durations) / len(all_durations)) if all_durations else None
            ),
            "p95_duration_ms": _p95(all_durations),
            "error_rate_pct": (
                round(data["error_count"] / total * 100, 1)
                if total > 0 else None
            ),
        }

    result = []
    # Include all canonical stages even if they have no data yet
    seen = set()
    empty = {"ok_durations": [], "error_durations": [], "ok_count": 0, "error_count": 0}
    for stage in PIPELINE_STAGES:
        seen.add(stage)
        data = stage_data.get(stage, empty)
        result.append(_build_stage_row(stage, data))

    # Append any unexpected stages recorded in telemetry but not in canonical list
    for stage, data in stage_data.items():
        if stage in seen:
            continue
        result.append(_build_stage_row(stage, data))

    return result


@router.get("/executions")
def get_executions(
    hours: int = Query(default=24, ge=0, le=720),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Paginated execution history.  Each row contains the check ID, status,
    verdict distribution, claim count, and duration — but NOT the URL or any
    claim text."""
    _ensure_schema()
    hours, limit, offset = int(hours), int(limit), int(offset)
    params_filter: list[Any] = []
    where_clause = ""
    if hours > 0:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        where_clause = "WHERE created_at >= ?"
        params_filter.append(cutoff)

    total_row = db.fetch_one(
        f"SELECT COUNT(*) AS cnt FROM reel_checks {where_clause}",
        tuple(params_filter),
    )
    total = dict(total_row)["cnt"] if total_row else 0

    rows = db.fetch_all(
        f"SELECT id, status, claims_json, created_at, completed_at "
        f"FROM reel_checks {where_clause} ORDER BY created_at DESC "
        f"LIMIT ? OFFSET ?",
        tuple(params_filter) + (limit, offset),
    )

    import json as _json

    executions = []
    for row in rows:
        d = dict(row)
        claims = _json.loads(d["claims_json"]) if d["claims_json"] else []
        verdict_counts: dict[str, int] = {}
        for c in claims:
            v = c.get("verdict", "unverifiable")
            verdict_counts[v] = verdict_counts.get(v, 0) + 1

        # Duration computation in Python for DB agnosticism
        duration_s: float | None = None
        if d["completed_at"] and d["created_at"]:
            try:
                t0 = datetime.fromisoformat(d["created_at"])
                t1 = datetime.fromisoformat(d["completed_at"])
                duration_s = round((t1 - t0).total_seconds(), 1)
            except Exception:
                pass

        executions.append({
            "id": d["id"],
            "status": d["status"],
            "claim_count": len(claims),
            "verdict_counts": verdict_counts,
            "created_at": d["created_at"],
            "completed_at": d["completed_at"],
            "duration_s": duration_s,
        })

    return {"total": total, "offset": offset, "limit": limit, "items": executions}


@router.get("/errors")
def get_errors(
    hours: int = Query(default=24, ge=0, le=720),
    limit: int = Query(default=30, ge=1, le=100),
) -> list[dict[str, Any]]:
    """Recent pipeline error events.  Returns only stage name, error type
    (class name, not message), duration, and timestamp — no URLs or claim
    text."""
    _ensure_schema()
    hours, limit = int(hours), int(limit)
    time_filter, time_params = _since_clause(hours)

    rows = db.fetch_all(
        f"SELECT check_id, stage, duration_ms, error_msg, recorded_at "
        f"FROM pipeline_events pe "
        f"WHERE status='error' {time_filter} "
        f"ORDER BY recorded_at DESC LIMIT ?",
        time_params + (limit,),
    )

    return [
        {
            "check_id": dict(r)["check_id"],
            "stage": dict(r)["stage"],
            "duration_ms": dict(r)["duration_ms"],
            # error_msg is stored as exception type name (≤512 chars) not full message
            "error_type": dict(r)["error_msg"],
            "recorded_at": dict(r)["recorded_at"],
        }
        for r in rows
    ]
