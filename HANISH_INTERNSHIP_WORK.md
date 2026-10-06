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

Status: NOT STARTED

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

Status: NOT STARTED

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

Status: NOT STARTED

Brief objective:
Create measurable visibility into system performance and reliability.

Track planned metrics:
* End-to-end latency (total duration from submission to final conclusion).
* Per-stage latency (acquisition, audio extraction, Whisper transcription, claim extraction, RAG retrieval, OpenAI/Groq verification, conclusion synthesis).
* Transcription duration and real-time factor (RTF).
* Claim extraction duration and token consumption.
* Retrieval duration (Qdrant intra-video context search and government source search).
* Web verification duration (OpenAI Responses web search latency and retry counts).
* FFmpeg processing time (audio DSP, clip cutting, timeline compilation, reel overlay compositing).
* API success/failure rates across endpoints and background runners.
* External API failures (Groq rate limits/429s, OpenAI timeouts, Qdrant connection issues).
* Processing-stage failures and retry exhaustion.
* Token/API usage where available (prompt tokens, completion tokens, search tool calls).
* Estimated AI cost where measurable (Groq API vs. OpenAI GPT-4.1 web search costs).
* Benchmark accuracy trends over time.
* Job throughput and concurrency capacity.

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
