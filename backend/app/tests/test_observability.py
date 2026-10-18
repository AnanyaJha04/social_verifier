"""
tests/test_observability.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Unit tests for the Observability API endpoints and the telemetry module.

All database I/O is replaced by deterministic in-memory mocks so no real
SQLite file or pipeline execution is required.  Tests are self-contained and
runnable offline.
"""
from __future__ import annotations

import importlib
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out external deps before importing the modules under test
# ---------------------------------------------------------------------------

def _make_settings_stub():
    stub = MagicMock()
    stub.database_url = None  # force SQLite path
    stub.data_dir = MagicMock()
    stub.qdrant_url = None
    return stub


def _install_stubs():
    """Install minimal module stubs so app.core.db and app.core.telemetry can
    be imported without the real database / config machinery."""
    settings_stub = _make_settings_stub()

    # app.core.config
    config_mod = types.ModuleType("app.core.config")
    config_mod.settings = settings_stub
    sys.modules.setdefault("app.core.config", config_mod)

    # app.core.db – in-memory SQLite-backed fake
    if "app.core.db" not in sys.modules:
        import sqlite3

        _conn = sqlite3.connect(":memory:", check_same_thread=False)
        _conn.row_factory = sqlite3.Row

        class _FakeDB:
            conn = _conn

            @staticmethod
            def execute(sql: str, params=()):
                sql = sql.replace("datetime('now')", "datetime('now')")
                _conn.execute(sql, params)
                _conn.commit()

            @staticmethod
            def fetch_one(sql: str, params=()):
                return _conn.execute(sql, params).fetchone()

            @staticmethod
            def fetch_all(sql: str, params=()):
                return _conn.execute(sql, params).fetchall()

            @staticmethod
            def get_conn():
                return _conn

        db_mod = types.ModuleType("app.core.db")
        db_mod.execute = _FakeDB.execute
        db_mod.fetch_one = _FakeDB.fetch_one
        db_mod.fetch_all = _FakeDB.fetch_all
        db_mod.get_conn = _FakeDB.get_conn
        sys.modules["app.core.db"] = db_mod


_install_stubs()

# Now import modules under test
from app.core import telemetry as tel_module  # noqa: E402
from app.api import observability as obs_module  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _now() -> datetime:
    return datetime.now(timezone.utc)


_REEL_CHECKS_DDL = """
CREATE TABLE IF NOT EXISTS reel_checks (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL DEFAULT 'https://example.com/reel',
    status TEXT NOT NULL DEFAULT 'done',
    claims_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT
);
"""


def _seed_schema():
    """Ensure tables exist in the in-memory DB."""
    db_mod = sys.modules["app.core.db"]
    conn = db_mod.get_conn()
    # Use executescript for multi-statement DDL
    conn.executescript(_REEL_CHECKS_DDL)
    conn.commit()
    # Now ensure telemetry schema via the individual-statement path
    tel_module._bootstrapped = False
    tel_module._ensure_schema()


def _insert_check(
    check_id: str,
    status: str = "done",
    claims_json: str | None = None,
    created_offset_hours: int = 0,
    duration_minutes: int = 2,
):
    db = sys.modules["app.core.db"]
    created = _iso(_now() - timedelta(hours=created_offset_hours))
    completed = _iso(
        _now() - timedelta(hours=created_offset_hours) + timedelta(minutes=duration_minutes)
    ) if status == "done" else None
    db.execute(
        "INSERT OR REPLACE INTO reel_checks (id, url, status, claims_json, created_at, completed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (check_id, "https://x.com/reel/1", status, claims_json, created, completed),
    )


def _insert_event(check_id: str, stage: str, status: str = "ok", duration_ms: int = 500, error_msg: str | None = None, offset_hours: int = 0):
    db = sys.modules["app.core.db"]
    recorded = _iso(_now() - timedelta(hours=offset_hours))
    import uuid
    db.execute(
        "INSERT INTO pipeline_events (id, check_id, stage, status, duration_ms, error_msg, recorded_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), check_id, stage, status, duration_ms, error_msg, recorded),
    )


# ---------------------------------------------------------------------------
# Setup / teardown
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clean_db():
    """Drop and recreate tables before each test for isolation."""
    db_mod = sys.modules["app.core.db"]
    conn = db_mod.get_conn()
    conn.executescript(
        "DROP TABLE IF EXISTS pipeline_events;"
        "DROP TABLE IF EXISTS reel_checks;"
    )
    conn.commit()
    tel_module._bootstrapped = False
    _seed_schema()
    yield


# ===========================================================================
# telemetry module tests
# ===========================================================================

class TestTelemetryRecordEvent:
    def test_event_persisted(self):
        tel_module.record_event("chk-1", "downloading", "ok", 300)
        db = sys.modules["app.core.db"]
        rows = db.fetch_all("SELECT * FROM pipeline_events WHERE check_id='chk-1'")
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["stage"] == "downloading"
        assert row["status"] == "ok"
        assert row["duration_ms"] == 300

    def test_error_message_truncated_to_512(self):
        long_msg = "X" * 1000
        tel_module.record_event("chk-2", "transcribing", "error", 100, long_msg)
        db = sys.modules["app.core.db"]
        row = dict(db.fetch_all("SELECT * FROM pipeline_events WHERE check_id='chk-2'")[0])
        assert len(row["error_msg"]) == 512

    def test_null_duration_allowed(self):
        tel_module.record_event("chk-3", "concluding", "ok", None)
        db = sys.modules["app.core.db"]
        row = dict(db.fetch_all("SELECT * FROM pipeline_events WHERE check_id='chk-3'")[0])
        assert row["duration_ms"] is None

    def test_storage_failure_does_not_raise(self):
        """Simulate a DB failure — record_event must swallow it silently."""
        with patch.object(sys.modules["app.core.db"], "execute", side_effect=RuntimeError("disk full")):
            # Must not raise
            tel_module.record_event("chk-9", "downloading", "ok", 100)


class TestTelemetryRecordStageContextManager:
    def test_ok_stage_records_duration(self):
        with tel_module.record_stage("chk-4", "transcribing"):
            pass
        db = sys.modules["app.core.db"]
        rows = db.fetch_all("SELECT * FROM pipeline_events WHERE check_id='chk-4'")
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["status"] == "ok"
        assert row["duration_ms"] is not None and row["duration_ms"] >= 0

    def test_exception_records_error_and_reraises(self):
        with pytest.raises(ValueError, match="boom"):
            with tel_module.record_stage("chk-5", "downloading"):
                raise ValueError("boom")
        db = sys.modules["app.core.db"]
        rows = db.fetch_all("SELECT * FROM pipeline_events WHERE check_id='chk-5'")
        assert len(rows) == 1
        row = dict(rows[0])
        assert row["status"] == "error"
        # Only the exception class name is stored, not the message
        assert row["error_msg"] == "ValueError"
        assert "boom" not in (row["error_msg"] or "")

    def test_error_msg_contains_class_name_not_message(self):
        """Sensitive data in exception message must not leak into telemetry."""
        secret_url = "https://secret-internal-server/private"
        with pytest.raises(RuntimeError):
            with tel_module.record_stage("chk-6", "downloading"):
                raise RuntimeError(f"Failed to connect to {secret_url}")
        db = sys.modules["app.core.db"]
        row = dict(db.fetch_all("SELECT * FROM pipeline_events WHERE check_id='chk-6'")[0])
        assert secret_url not in (row["error_msg"] or "")
        assert row["error_msg"] == "RuntimeError"


# ===========================================================================
# Observability API endpoint tests
# ===========================================================================

class TestSummaryEndpoint:
    def test_empty_db_returns_zeros(self):
        result = obs_module.get_summary(hours=24)
        assert result["total_checks"] == 0
        assert result["done"] == 0
        assert result["error"] == 0
        assert result["success_rate_pct"] is None

    def test_counts_all_checks(self):
        _insert_check("c1", "done")
        _insert_check("c2", "done")
        _insert_check("c3", "error")
        result = obs_module.get_summary(hours=0)
        assert result["total_checks"] == 3
        assert result["done"] == 2
        assert result["error"] == 1
        assert result["success_rate_pct"] == pytest.approx(66.7, abs=0.1)

    def test_time_filter_excludes_old_checks(self):
        _insert_check("c-old", "done", created_offset_hours=48)
        _insert_check("c-new", "done", created_offset_hours=0)
        result = obs_module.get_summary(hours=24)
        assert result["total_checks"] == 1
        assert result["done"] == 1

    def test_hours_zero_means_all_time(self):
        _insert_check("c-old2", "done", created_offset_hours=500)
        result = obs_module.get_summary(hours=0)
        assert result["total_checks"] == 1

    def test_avg_duration_computed(self):
        _insert_check("c-dur", "done", duration_minutes=4)
        result = obs_module.get_summary(hours=0)
        assert result["avg_check_duration_s"] is not None
        assert result["avg_check_duration_s"] > 0

    def test_pipeline_event_counts(self):
        _insert_event("c1", "downloading", "ok", 400)
        _insert_event("c1", "transcribing", "error", 100, "RuntimeError")
        result = obs_module.get_summary(hours=0)
        assert result["total_pipeline_events"] == 2
        assert result["pipeline_error_rate_pct"] == pytest.approx(50.0)

    def test_period_hours_returned(self):
        result = obs_module.get_summary(hours=6)
        assert result["period_hours"] == 6


class TestStageStatsEndpoint:
    def test_all_canonical_stages_present_even_without_data(self):
        result = obs_module.get_stage_stats(hours=0)
        stage_names = {s["stage"] for s in result}
        for stage in obs_module.PIPELINE_STAGES:
            assert stage in stage_names

    def test_durations_aggregated_correctly(self):
        for ms in [100, 200, 300]:
            _insert_event("cx", "transcribing", "ok", ms)
        result = obs_module.get_stage_stats(hours=0)
        tr = next(s for s in result if s["stage"] == "transcribing")
        assert tr["ok_count"] == 3
        assert tr["avg_duration_ms"] == 200  # (100+200+300)/3

    def test_error_rate_correct(self):
        _insert_event("cx", "downloading", "ok", 500)
        _insert_event("cx", "downloading", "error", 200, "TimeoutError")
        result = obs_module.get_stage_stats(hours=0)
        dl = next(s for s in result if s["stage"] == "downloading")
        assert dl["error_rate_pct"] == pytest.approx(50.0)
        assert dl["error_count"] == 1
        assert dl["ok_count"] == 1

    def test_p95_computed(self):
        durations = list(range(10, 210, 10))  # 10..200, 20 values
        for ms in durations:
            _insert_event("cx", "concluding", "ok", ms)
        result = obs_module.get_stage_stats(hours=0)
        con = next(s for s in result if s["stage"] == "concluding")
        # p95 of 20 values = value at index 18 (0-indexed) = 190
        assert con["p95_duration_ms"] == 190

    def test_stage_with_no_events_returns_none_durations(self):
        result = obs_module.get_stage_stats(hours=0)
        dl = next(s for s in result if s["stage"] == "downloading")
        assert dl["avg_duration_ms"] is None
        assert dl["p95_duration_ms"] is None
        assert dl["error_rate_pct"] is None

    def test_time_filter_applies(self):
        _insert_event("cx", "transcribing", "ok", 300, offset_hours=0)
        _insert_event("cx", "transcribing", "ok", 300, offset_hours=48)
        result_24h = obs_module.get_stage_stats(hours=24)
        tr = next(s for s in result_24h if s["stage"] == "transcribing")
        assert tr["ok_count"] == 1

    def test_null_duration_events_counted_in_totals_and_rates_without_affecting_durations(self):
        """Defect A regression test: events with null duration must be counted in
        total_events, ok_count, error_count, and error_rate_pct, but excluded from
        avg_duration_ms and p95_duration_ms rather than dropped entirely or treated as 0ms."""
        _insert_event("cx", "downloading", "ok", duration_ms=None)
        _insert_event("cx", "downloading", "error", duration_ms=None, error_msg="NetworkError")
        _insert_event("cx", "downloading", "ok", duration_ms=200)

        result = obs_module.get_stage_stats(hours=0)
        dl = next(s for s in result if s["stage"] == "downloading")
        assert dl["total_events"] == 3
        assert dl["ok_count"] == 2
        assert dl["error_count"] == 1
        assert dl["error_rate_pct"] == pytest.approx(33.3, abs=0.1)
        # Average must be 200ms (only the 1 non-null observation), NOT 66.7ms
        assert dl["avg_duration_ms"] == 200
        assert dl["p95_duration_ms"] == 200

    def test_stage_with_only_null_duration_events(self):
        _insert_event("cx", "extracting_claims", "ok", duration_ms=None)
        result = obs_module.get_stage_stats(hours=0)
        st = next(s for s in result if s["stage"] == "extracting_claims")
        assert st["total_events"] == 1
        assert st["ok_count"] == 1
        assert st["error_count"] == 0
        assert st["error_rate_pct"] == 0.0
        assert st["avg_duration_ms"] is None
        assert st["p95_duration_ms"] is None

    def test_hours_parameter_coerced(self):
        _insert_event("cx", "downloading", "ok", 150)
        result = obs_module.get_stage_stats(hours="24")  # type: ignore
        dl = next(s for s in result if s["stage"] == "downloading")
        assert dl["ok_count"] == 1


class TestExecutionsEndpoint:
    def test_empty_returns_empty_items(self):
        result = obs_module.get_executions(hours=0, limit=10, offset=0)
        assert result["items"] == []
        assert result["total"] == 0

    def test_items_contain_no_url(self):
        _insert_check("c1", "done")
        result = obs_module.get_executions(hours=0, limit=50, offset=0)
        item = result["items"][0]
        assert "url" not in item

    def test_verdict_counts_computed(self):
        claims = json.dumps([
            {"verdict": "true"},
            {"verdict": "false"},
            {"verdict": "true"},
        ])
        _insert_check("c1", "done", claims_json=claims)
        result = obs_module.get_executions(hours=0, limit=50, offset=0)
        item = result["items"][0]
        assert item["claim_count"] == 3
        assert item["verdict_counts"]["true"] == 2
        assert item["verdict_counts"]["false"] == 1

    def test_pagination_offset(self):
        for i in range(5):
            _insert_check(f"c{i}", "done", created_offset_hours=i)
        result = obs_module.get_executions(hours=0, limit=2, offset=2)
        assert len(result["items"]) == 2
        assert result["total"] == 5
        assert result["offset"] == 2

    def test_duration_computed(self):
        _insert_check("c1", "done", duration_minutes=3)
        result = obs_module.get_executions(hours=0, limit=50, offset=0)
        item = result["items"][0]
        assert item["duration_s"] is not None
        assert item["duration_s"] >= 0

    def test_error_check_has_null_duration(self):
        _insert_check("c1", "error")
        result = obs_module.get_executions(hours=0, limit=50, offset=0)
        item = result["items"][0]
        assert item["duration_s"] is None

    def test_time_filter(self):
        _insert_check("c-old", "done", created_offset_hours=50)
        _insert_check("c-new", "done", created_offset_hours=0)
        result = obs_module.get_executions(hours=24, limit=50, offset=0)
        assert result["total"] == 1
        assert result["items"][0]["id"] == "c-new"


class TestErrorsEndpoint:
    def test_empty_returns_empty_list(self):
        result = obs_module.get_errors(hours=24, limit=10)
        assert result == []

    def test_only_error_events_returned(self):
        _insert_event("c1", "downloading", "ok", 400)
        _insert_event("c1", "transcribing", "error", 100, "RuntimeError")
        result = obs_module.get_errors(hours=0, limit=10)
        assert len(result) == 1
        assert result[0]["stage"] == "transcribing"

    def test_url_not_in_response(self):
        _insert_event("c1", "downloading", "error", 100, "TimeoutError")
        result = obs_module.get_errors(hours=0, limit=10)
        for item in result:
            assert "url" not in item

    def test_error_type_is_class_name(self):
        _insert_event("c1", "extracting_claims", "error", 200, "ValueError")
        result = obs_module.get_errors(hours=0, limit=10)
        assert result[0]["error_type"] == "ValueError"

    def test_limit_respected(self):
        for i in range(20):
            _insert_event(f"c{i}", "downloading", "error", 100, "TimeoutError")
        result = obs_module.get_errors(hours=0, limit=5)
        assert len(result) <= 5

    def test_time_filter(self):
        _insert_event("c-old", "downloading", "error", 100, "TimeoutError", offset_hours=48)
        _insert_event("c-new", "downloading", "error", 100, "TimeoutError", offset_hours=0)
        result = obs_module.get_errors(hours=24, limit=10)
        assert len(result) == 1
        assert result[0]["check_id"] == "c-new"


@pytest.mark.asyncio
class TestObservabilityAuth:
    @pytest.mark.parametrize("path", [
        "/api/observability/summary",
        "/api/observability/stages",
        "/api/observability/executions",
        "/api/observability/errors",
    ])
    async def test_unauthenticated_request_rejected(self, async_client, path):
        resp = await async_client.get(path)
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Not authenticated"}

    async def test_authenticated_request_allowed_with_bearer_token(self, async_client):
        from app.core.auth import SESSION_TOKEN
        resp = await async_client.get(
            "/api/observability/summary",
            headers={"Authorization": f"Bearer {SESSION_TOKEN}"},
        )
        assert resp.status_code == 200
        assert "total_checks" in resp.json()

    async def test_authenticated_request_allowed_with_cookie(self, async_client):
        from app.core.auth import SESSION_TOKEN
        resp = await async_client.get(
            "/api/observability/summary",
            cookies={"lc_session": SESSION_TOKEN},
        )
        assert resp.status_code == 200
        assert "total_checks" in resp.json()

