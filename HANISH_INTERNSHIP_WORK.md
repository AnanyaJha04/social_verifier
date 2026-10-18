# Hanish — Internship Development & Testing Work

## Project

Social Verifier

## Role

Development + Testing

## Objective

Improve and mature the Social Verifier project by developing and validating an automated evaluation/benchmark framework, an adversarial test suite, and a comprehensive observability system. My responsibility is to provide empirical, reproducible evidence of pipeline accuracy, latency, failure modes, and security/reliability boundaries without relying on assumptions or superficial checks.

## Current Project Baseline

Based strictly on an empirical analysis of the repository source code and configuration:

* **Dual Architecture**: The repository contains two distinct pipeline subsystems unified under a single FastAPI service and React frontend:
  1. **Social Verifier / Reel Check (`app/verifier`)**: A one-shot background pipeline triggered via `POST /api/verify` (or `POST /api/verify/batch`) that uses `yt-dlp` to download social video clips, FFmpeg to extract audio, Groq Whisper (`whisper-large-v3-turbo`) to transcribe speech, Groq (`gpt-oss-120b`) to extract checkable claims, Qdrant and local embeddings for intra-video context and official government sources (`gov_sources`), and OpenAI Responses API (`gpt-4.1` with web search tool) or Groq fallback to verify claims. Supporting tools generate ReportLab fact-check PDFs, debunk scripts, frame-accurate claim clips via FFmpeg re-encoding, and a vertical video editor with timeline compilation and Instagram kit generation.
  2. **Live News Cutter (`app/session_runner`, `app/ingest`, `app/segmentation`)**: A streaming pipeline that continuously ingests HLS/YouTube Live streams using supervised FFmpeg subprocesses into 10s `.ts` and `.wav` segments, aggregates audio into ~10-minute batches (`settings.batch_window_seconds = 600`), runs WebRTC VAD, applies DSP audio normalization, transcribes via Groq Whisper, detects news story boundaries using Groq LLM with in-memory SQLite/Postgres cosine-similarity RAG over earlier clips, cuts stream clips with FFmpeg, and streams live updates to the frontend via an in-memory WebSocket event bus.
* **Testing State**:
  * Unit/Integration tests are minimal: only two files in `app/tests/` ([test_sessions.py](file:///e:/RIG_360/social/social_verifier/backend/app/tests/test_sessions.py) and [test_session_runner.py](file:///e:/RIG_360/social/social_verifier/backend/app/tests/test_session_runner.py)) totaling 54 lines of code with placeholder mocks.
  * Zero tests exist for the verification pipeline (`app/verifier/*`), claim extraction, claim matching, web-search verification, debunk script generation, editor timeline compilation, or Qdrant RAG retrieval.
  * Frontend testing is limited to an unmaintained Playwright smoke test script ([smoke_test.mjs](file:///e:/RIG_360/social/social_verifier/frontend/scripts/smoke_test.mjs)).
* **Observability State**:
  * Basic standard library `logging.getLogger` writing unstructured stdout logs.
  * No structured metrics, latency instrumentation, token count tracking, cost tracking, accuracy evaluation, or tracing.
  * Processing stage tracking exists only as string status updates (`downloading`, `transcribing`, `extracting_claims`, `verifying_claims`, `concluding`, `done`, `error`) stored in database tables.

## Planned Work

### 1. Automated Evaluation / Benchmark Framework

Status: VALIDATED

**Implementation Details:**
- **Architecture**: A dedicated benchmark framework was built in `backend/benchmark/` with components for schema validation, isolated offline/pipeline execution, calculation of metrics (precision, recall, F1, accuracy, confusion matrices), and generation of Markdown/JSON reports.
- **Dataset Schema**: A robust Pydantic schema version `1.0` was designed avoiding ground-truth leakage and rejecting malformed inputs.
- **Artifacts**: Configurable JSON artifacts and human-readable Markdown reports are automatically written to `backend/benchmark_reports/`. Baseline regression checks prevent performance regressions.
- **Execution**: The CLI tool allows selecting datasets and running offline tests using synthetic deterministic fixtures.

**Validation Evidence:**
- **Command:** `python scripts/run_benchmark.py --dataset benchmark/datasets/synthetic_dataset.json --mode offline`
- **Result:** Completed successfully. Processed 3 cases. Passed: 3, Failed: 0, Errored: 0. Artifacts generated at `benchmark_reports/benchmark_202610d133139-dcc312.md`. Results use synthetic fixtures and mock models to confirm framework correctness, not actual model accuracy.
- **Test Command:** `pytest`
- **Test Result:** All 9 items passed (5 benchmark unit tests + 4 existing session runner tests). Exit code 0. Original test suite remains strong.

**Limitations & Remaining Work:**
- Real pipeline testing requires opt-in mode with live LLM credits and is pending integration with the continuous deployment setup.
- "Not Addressed" government source assertions are untracked by aggregate metrics.

Brief objective:
Create a repeatable benchmark system capable of evaluating the verification pipeline against known/ground-truth cases.

Planned activities:
* Define benchmark dataset structure (curated social video clips, audio snippets, known manuscripts, and ground-truth claims/verdicts).
* Define ground-truth schema (expected claims, verbatim quotes, timestamps, consensus verdicts: `true`, `false`, `misleading`, `partially true`, `unverifiable`, and key factual citations).
* Build automated execution pipeline to run verification benchmarks deterministically against test fixtures or recorded network responses.
* Measure claim extraction performance (precision, recall, quote fidelity, over-segmentation vs. missed claims).
* Measure verdict performance (verdict classification accuracy, confusion matrix, reasoning alignment, hallucination rate).
* Measure timestamp/clip accuracy where applicable (fuzzy match score, alignment between claim boundary and spoken audio).
* Generate evaluation reports (automated markdown/JSON summaries detailing benchmark runs, regression status, and discrepancies).
* Add regression testing into CI/local test workflows.

### 2. Adversarial Test Suite

Status: VALIDATED

**Implementation Details:**
- **Architecture**: A dedicated adversarial test suite was established under `backend/app/tests/adversarial/` organized by categories (A through G) across 7 specialized test modules:
  - `test_category_a_claims.py`: Direct assertions, paraphrased assertions, questions, clickbait with zero claims, multiple compound claims, opinion mixed with fact, incomplete quotations, duplicate claims, and Whisper segment boundary matching.
  - `test_category_b_injection.py`: Untrusted transcript injection strings, jailbreak prompts, fake `SYSTEM:`/`DEVELOPER:` role delimiters, schema hijacking, and context block bullet formatting.
  - `test_category_c_parsing.py`: Primary verdict labels, unsupported labels, missing verdict/analysis/source keys, markdown code-fence stripping, malformed/truncated JSON recovery, extra fields, and government verification parsing.
  - `test_category_d_network.py`: URL scheme validation, length limits, credentialed URLs, loopback/private IPv4/IPv6 handling, argument list subprocess safety (preventing shell injection), missing audio track detection, and authenticated API endpoint boundaries.
  - `test_category_e_media.py`: FFmpeg subprocess checking via `run_checked` (capturing stderr on non-zero exits, missing binaries, timeouts), audio extraction arguments, DSP filter chain application, manifest file unlinking in `concat_wavs`, and clip cutting bounds.
  - `test_category_f_transcription.py`: Whisper segment timestamp-to-absolute offset conversions, whole-chunk fallback, empty/whitespace responses, and manuscript timestamp formatting.
  - `test_category_g_resilience.py`: Groq rate limit retry parsing and max delay guards, OpenAI missing key and connection error fallbacks, non-LLM conclusion tally generation, Qdrant retrieval failure isolation, and background job failure DB status updates.
- **Benchmark Integration**: Integrated deterministic adversarial cases into `backend/benchmark/datasets/adversarial_dataset.json` evaluating rhetorical questions, clickbait, opinion-fact mixtures, and prompt injection through the benchmark runner.
- **Security & Reliability Findings Identified**:
  - `FINDING-ADV-01`: Absence of SSRF and Private IP blocklisting in `_validate_url` (`app/models/schemas.py`). Confirmed and documented with regression tests in `test_category_d_network.py`.
  - `FINDING-ADV-02`: In-memory prompt construction string interpolation for `claim` and `quote` (`app/verifier/claims.py`) lacks delimiter escaping. Confirmed and tested in `test_category_b_injection.py`.
  - `FINDING-ADV-03`: Unsupported model verdict preservation without strict validation against `VerdictLabel`. Confirmed and tested in `test_category_c_parsing.py`.

**Validation Evidence:**
- **Adversarial Test Suite Command:** `pytest app/tests/adversarial`
  - **Result:** 98 passed, 0 failed, 80 deprecation warnings in 0.60s. Exit code 0.
- **Full Test Suite Command:** `pytest`
  - **Result:** 107 passed (98 adversarial + 5 benchmark + 4 session), 0 failed, 80 warnings in 0.80s. Exit code 0.
- **Benchmark Adversarial Run Command:** `python scripts/run_benchmark.py --dataset benchmark/datasets/adversarial_dataset.json --mode offline`
  - **Result:** 4/4 cases processed and passed in offline mode. Reports generated at `benchmark_reports/benchmark_202610d161852-6a9539.md`.

**Mocked vs. Real Component Coverage & Limitations:**
- Mocked components: Groq chat completions, OpenAI Responses web search, Groq Whisper transcription API, yt-dlp binary downloads, Qdrant vector database connections.
- Real components executed: Pydantic schemas and validators, URL sanitizers, quote-to-segment fuzzy diff matching (`attach_clip_times`), JSON response deserializers and fence strippers, FFmpeg argument assembly and duration clamping, temporary directory cleanup, database status updates, and FastAPI router authentication middleware.
- Limitations: Text-based mock fixtures do not evaluate raw acoustic speech recognition accuracy under background acoustic noise, accent variability, or multi-speaker overlapping audio. A separate physical audio corpus is required for true acoustic evaluation.

Brief objective:
Create controlled adversarial test cases to identify weaknesses in the verification pipeline.

Planned categories:
* Misleading wording and clickbait framing.
* Paraphrased claims and indirect statements.
* Ambiguous claims with subjective or dual interpretations.
* Outdated information presented as breaking or current news.
* Incomplete context and selective audio/quote omissions.
* Contradictory evidence (competing authoritative sources or disputed statistics).
* Noisy audio, low signal-to-noise ratio, room reverb, and background music/chants.
* Accents and regional speech variation (Indian English, Hinglish accents, regional dialects).
* Rapid speech, overlapping speakers, and interruptions.
* OCR/text-in-video cases (claims appearing only on screen tickers or text cards without spoken audio).
* Prompt-injection-like content inside source material (transcripts containing LLM jailbreaks, system instruction overrides, or format corruptions).
* Malicious/untrusted URLs where appropriate (SSRF targets, private IP schemes, malformed URLs, non-video responses).
* Malformed inputs (corrupted audio headers, empty files, truncated downloads).
* Resource-heavy inputs (extremely long videos, very high-frequency claim density).

### 3. Observability Dashboard

Status: VALIDATED

**Implementation Details:**

- **Backend telemetry module** (`backend/app/core/telemetry.py`): Lightweight, append-only instrumentation layer. Creates a single new `pipeline_events` SQLite/Postgres table (zero coupling to existing schema). Provides a `record_stage(check_id, stage)` context manager that wraps pipeline stages: records correlation ID, stage name, duration in milliseconds, and sanitised error type (exception class name only — never exception messages, URLs, or claim text) on failure. Storage failures are caught and logged without affecting the pipeline.

- **Pipeline instrumentation** (`backend/app/verifier/runner.py`): All five canonical pipeline stages are now instrumented:
  - `downloading` — wraps `download_clip`
  - `transcribing` — wraps `extract_audio` + `build_manuscript`
  - `extracting_claims` — wraps `extract_claims`
  - `verifying_claims` — wraps `verify_claim` (once per claim)
  - `concluding` — wraps `generate_conclusion`

- **Read-only observability API** (`backend/app/api/observability.py`): Four authenticated GET endpoints (protected by existing `AuthMiddleware`) under `/api/observability/`:
  - `GET /api/observability/summary?hours=N` — overall counts, success rate, pipeline event error rate, avg check duration
  - `GET /api/observability/stage-stats?hours=N` — per-stage avg/p95 duration, ok/error counts, error rate
  - `GET /api/observability/executions?hours=N&limit=L&offset=O` — paginated execution history with verdict distribution (no URLs or claim text)
  - `GET /api/observability/errors?hours=N&limit=L` — recent sanitised pipeline error events (exception class name only)

  All endpoints support a `hours` time-range filter (0 = all time, up to 720h). Duration and verdict aggregation is computed in Python for full SQLite/Postgres compatibility.

- **Frontend dashboard** (`frontend/src/pages/ObservabilityPage.tsx`): Premium `/observability` route added to the React app:
  - Time-range picker (1h / 6h / 24h / 7d / All time), auto-refreshes every 30 s
  - Overview card row: total checks, success rate, avg end-to-end duration, total pipeline events / event error rate
  - Stage performance section: horizontal stacked bar per stage (green = ok, red = error) with avg/p95 latency annotations
  - Execution history table: paginated, clickable rows linking to `/verify/:checkId`, verdict pip visualisation per execution (no URL exposure)
  - Recent errors panel: sanitised error type + stage + timing, no claim or URL data

- **NavBar** (`frontend/src/components/ui/NavBar.tsx`): "Observatory" tab added adjacent to Sessions and Verifier, with active state detection.

- **API types & client** (`frontend/src/api/types.ts`, `frontend/src/api/client.ts`): Four TypeScript interfaces (`ObsSummary`, `ObsStageStats`, `ObsExecutions`, `ObsExecution`, `ObsErrorEvent`) and four corresponding `api.getObs*()` functions added.

- **Tests** (`backend/app/tests/test_observability.py`): 42 unit and integration tests covering:
  - Telemetry: event persistence, 512-char error truncation, null duration, storage-failure suppression, context manager timing, exception-message redaction
  - `/summary`: empty DB, status counts, time-filter, all-time mode, avg duration, event rates
  - `/stage-stats`: canonical stage presence, duration aggregation, error rate, p95, null duration non-zero handling, time-filter, parameter coercion
  - `/executions`: empty, no-URL guarantee, verdict aggregation, pagination, duration, error check null duration, time-filter
  - `/errors`: empty, error-only filter, no-URL guarantee, error type field, limit, time-filter
  - Authentication: 401 unauthenticated enforcement across all 4 endpoints, Bearer token authorization, session cookie authorization

**Independent Validation Audit & Defect Remediation (2026-10-17):**
- **Defect A (Medium — Fixed)**: `get_stage_stats` in `backend/app/api/observability.py` discarded events with `duration_ms=None` from `total_events`, `ok_count`, and `error_count`. Separated counting from duration lists; refactored to `_build_stage_row` helper ensuring null durations are counted towards events and error rates without distorting average/p95 latencies.
- **Defect B (Medium — Fixed)**: `get_summary` and `get_stage_stats` lacked integer coercion for `hours` (`int(hours)`), causing potential type mismatch when called directly or in programmatic testing. Added explicit `int(hours)` coercion matching `get_executions` and `get_errors`.
- **Defect C (Medium — Fixed)**: `frontend/src/pages/ObservabilityPage.tsx` silently rendered zero/empty state on API fetch failure (401/500). Added global error banner (`#obs-error-banner`) and explicit error fallbacks for overview stats, stage bars, execution history table, and recent errors panel.
- **Defect D (Low — Fixed)**: Dead code in `_since_clause()` where an ISO-formatted cutoff was calculated and immediately overwritten by strftime. Removed unused calculation.

**Validation Evidence:**
- **Test Command:** `pytest app/tests/` (all tests including benchmark, adversarial, session, and observability suites)
- **Result:** 164 passed, 0 failed, 89 warnings in 1.59s. Exit code 0. (42 observability tests + 122 pre-existing tests.)
- **Frontend build:** `npm run build` — exit code 0, 0 TypeScript errors, 99 modules transformed, bundle size 342.7 kB.

**Security / Privacy Properties:**
- No URLs, claim text, transcripts, or API keys appear in telemetry storage or API responses.
- Error storage contains only exception class names (≤512 chars), not exception messages.
- All observability endpoints are gated by the existing `AuthMiddleware` Bearer/cookie token check (tested: all 4 endpoints return 401 when unauthenticated).
- Execution history exposes only check ID, terminal status, claim count, verdict distribution, and timing — no source URLs.

**Known Limitations:**
- Single-user authentication (`rig360media`): No multi-tenant role-based access control (RBAC); all authenticated users share the same dashboard view.
- Per-stage token counts and AI cost tracking are not implemented (require upstream API response metering not yet exposed by the pipeline).
- Benchmark accuracy trend over time is tracked separately via the benchmark runner, not yet integrated into the dashboard.
- Real-time WebSocket streaming of live pipeline events is deferred to a future iteration.

## Future Enhancements

These improvements represent valuable architectural expansions outside my immediate internship scope:
* Video OCR / Vision Model Ingestion: Ingest visual text cards, tickers, and graphics using multimodal models (GPT-4o or Whisper-vision) to capture non-spoken claims.
* Speaker Diarization: Incorporate pyannote.audio or similar speaker diarization into Whisper transcription to attribute specific claims to distinct speakers in debates or panels.
* Production Distributed Job Queue: Migrate in-process `asyncio.create_task` background runners to Celery, ARQ, or Redis Queue with Redis/RabbitMQ backing to enable persistence across server restarts and worker scaling.
* Persistent Media Storage: Replace local disk storage (`data_dir`) with S3/GCS object storage to allow deployment on stateless container environments.
* Multi-user Authentication & RBAC: Upgrade the single hardcoded user (`rig360media`) to a secure database-backed multi-tenant auth system with granular role-based permissions and per-user API rate limiting.

## Work Status Rules

Use these statuses consistently:
* NOT STARTED
* IN PROGRESS
* IMPLEMENTED
* TESTING
* VALIDATED
* BLOCKED
* DEFERRED

For every future update, preserve the history and change only the relevant status/details.

## Change Log

| Date | Work Item | Change | Status | Evidence |
| ---- | --------- | ------ | ------ | -------- |
| 2026-10-06 | Repository Baseline & Work Tracker | Established full repository architectural baseline and created initial internship work plan. | VALIDATED | Comprehensive static analysis of codebase; created `HANISH_INTERNSHIP_WORK.md`. |
| 2026-10-8 | Automated Evaluation / Benchmark Framework | Implemented isolated benchmark runner, synthetic fixtures, schema validation, report generation, and regression baseline mechanics in `backend/benchmark/`. | VALIDATED | `pytest` passed 9/9 tests (exit code 0); `run_benchmark.py` ran successfully on synthetic fixtures with 3/3 passed. Framework verified. |
| 2026-10-17 | Adversarial Test Suite | Implemented 98 adversarial and resilience tests covering categories A through G, integrated adversarial benchmark dataset, and documented confirmed security findings. | VALIDATED | `pytest` passed 107/107 tests (98 adversarial + 9 existing, exit code 0); `run_benchmark.py` ran successfully on `adversarial_dataset.json` with 4/4 passed (exit code 0). |
| 2026-10-17 | Security Finding Remediation | Remediated 3 findings: SSRF URL boundary with DNS resolution guard (`app/core/url_security.py`), XML untrusted data prompt isolation (`claims.py`), and strict canonical verdict validation/normalization (`claims.py`). Added 15 regression tests. | VALIDATED | `pytest` passed 122/122 tests (exit code 0); `run_benchmark.py` ran 3/3 synthetic and 4/4 adversarial cases passed (exit code 0). |
| 2026-10-17 | Observability Dashboard | Implemented telemetry module with `pipeline_events` table, instrumented 5 pipeline stages in `runner.py`, created 4 read-only API endpoints under `/api/observability/`, built premium React dashboard (ObservabilityPage) with time-range filter, stat cards, stage perf bars, execution history table, and error panel; added NavBar Observatory tab. | VALIDATED | `pytest` passed 155/155 tests (33 new + 122 pre-existing, exit code 0); `npm run build` passed with 0 TypeScript errors (exit code 0). |
| 2026-10-17 | Observability Dashboard Validation Audit | Conducted independent validation audit across 8 criteria. Remediated 4 defects: null duration event dropping in stage stats (`observability.py`), hours parameter coercion, missing error handling in frontend panels (`ObservabilityPage.tsx`), and dead code. Added 9 regression tests (42 total obs tests). Verified auth, privacy, persistence, timing, and job-level metrics. | VALIDATED | `pytest app/tests/` passed 164/164 tests (exit code 0); `npm run build` passed with 0 TS errors (exit code 0). |


