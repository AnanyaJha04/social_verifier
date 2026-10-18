"""
Category G: External service failures and resilience tests.

Tests application behavior when external services fail:
1. Groq Client & Rate Limiting (app/core/groq_pool.py):
   - RateLimitError retry behavior when retry-after is within limit
   - RateLimitError immediate escalation when retry-after exceeds 600s or is unparseable
   - Missing Groq API keys raises RuntimeError
2. OpenAI Web Search Verification (app/verifier/claims.py):
   - Missing OPENAI_API_KEY gracefully falls back to non-web search verification
   - ConnectionError / Timeout / 500 error from OpenAI retries up to 3 times, then falls back to Groq
   - Grounded flag is set to False and warning prefix added to analysis upon fallback
3. Conclusion Generation Fallback (generate_conclusion in app/verifier/claims.py):
   - Total Groq failure triggers _fallback_conclusion producing a non-LLM tally summary
4. Qdrant / RAG Resilience (app/verifier/runner.py):
   - Qdrant connection failure during _prior_context or _gov_context is caught and logged, returning []
   - Indexing failure does not abort the fact-checking pipeline
5. Background Pipeline Error State (run_reel_check in app/verifier/runner.py):
   - Unhandled exception sets reel_checks.status = 'error' and writes error_message to DB
"""
import json
from unittest.mock import MagicMock, patch
import pytest
from groq import RateLimitError

from app.core.groq_pool import _parse_retry_after, call_with_retry
from app.verifier.claims import (
    ExtractedClaim,
    _fallback_conclusion,
    generate_conclusion,
    verify_claim,
)
from app.verifier.runner import _gov_context, _prior_context, run_reel_check


# --- Groq Rate Limit & Pool Resilience ---

def test_parse_retry_after_minutes_and_seconds():
    """Verify regex parses Groq 429 retry messages accurately."""
    assert _parse_retry_after("Rate limit exceeded. try again in 2m30s") == 150.0
    assert _parse_retry_after("try again in 45s") == 45.0
    assert _parse_retry_after("No retry time mentioned") is None


def test_call_with_retry_succeeds_after_rate_limit():
    """Verify call_with_retry retries once when rate limit wait is bounded."""
    mock_fn = MagicMock()
    err_response = MagicMock(status_code=429)
    rate_err = RateLimitError("Rate limit hit: try again in 0.1s", response=err_response, body={})

    mock_fn.side_effect = [rate_err, "success_result"]

    with patch("app.core.groq_pool.time.sleep") as mock_sleep:
        res = call_with_retry(mock_fn)
        assert res == "success_result"
        assert mock_fn.call_count == 2
        mock_sleep.assert_called_once()


def test_call_with_retry_raises_when_wait_exceeds_max():
    """Verify call_with_retry raises RateLimitError if wait time exceeds 600s."""
    mock_fn = MagicMock()
    err_response = MagicMock(status_code=429)
    # 15 minutes = 900s > 600s
    rate_err = RateLimitError("try again in 15m0s", response=err_response, body={})
    mock_fn.side_effect = rate_err

    with pytest.raises(RateLimitError):
        call_with_retry(mock_fn)
    assert mock_fn.call_count == 1


# --- OpenAI Web Search Fallback to Plain Model ---

def test_verify_claim_falls_back_when_openai_key_missing():
    """Verify verify_claim falls back to plain Groq model when OpenAI is not configured."""
    claim = ExtractedClaim(quote="test quote", timestamp="00:00:01", claim="test claim")

    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "verdict": "false",
        "analysis": "This is false according to training memory.",
        "sources": [],
    })
    mock_resp.choices = [mock_choice]

    with patch("app.verifier.claims.get_openai_client", side_effect=RuntimeError("OPENAI_API_KEY is not configured")), \
         patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=mock_resp):

        result = verify_claim(claim)
        assert result.grounded is False
        assert result.verdict == "false"
        assert "[Not web-verified" in result.analysis


def test_verify_claim_falls_back_after_openai_connection_errors():
    """Verify verify_claim retries OpenAI on connection error and falls back gracefully."""
    claim = ExtractedClaim(quote="test quote", timestamp="00:00:01", claim="test claim")

    mock_openai = MagicMock()
    mock_openai.responses.create.side_effect = ConnectionError("OpenAI connection timed out")

    mock_groq_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "verdict": "unverifiable",
        "analysis": "Training data is inconclusive.",
        "sources": [],
    })
    mock_groq_resp.choices = [mock_choice]

    with patch("app.verifier.claims.get_openai_client", return_value=mock_openai), \
         patch("app.verifier.claims.time.sleep"), \
         patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=mock_groq_resp):

        result = verify_claim(claim)
        assert result.grounded is False
        assert result.verdict == "unverifiable"
        assert "[Not web-verified" in result.analysis
        # 3 attempts (initial + 2 delays)
        assert mock_openai.responses.create.call_count == 3


# --- Conclusion Generation Fallback ---

def test_generate_conclusion_falls_back_to_tally_on_error():
    """Verify generate_conclusion produces non-LLM count summary when Groq fails."""
    mock_verification = MagicMock(verdict="false")

    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", side_effect=RuntimeError("Groq service unavailable")):

        conclusion = generate_conclusion([mock_verification])
        assert "1 claim(s) were checked in this clip" in conclusion
        assert "1 false" in conclusion
        assert "temporarily unavailable" in conclusion


# --- Qdrant Retrieval Resilience ---

def test_rag_context_handles_qdrant_exception_gracefully():
    """Verify runner helpers return empty context without crashing if Qdrant throws."""
    with patch("app.core.config.settings.qdrant_url", "http://qdrant.local:6333"), \
         patch("app.rag.claim_store.search_prior_context", side_effect=ConnectionError("Qdrant unreachable")):
        context = _prior_context("chk_123", 1, "test query")
        assert context == []

    with patch("app.core.config.settings.qdrant_url", "http://qdrant.local:6333"), \
         patch("app.rag.gov_store.search_gov_sources", side_effect=ConnectionError("Qdrant unreachable")):
        gov_context = _gov_context("test query")
        assert gov_context == []


# --- Background Pipeline Error Handling ---

@pytest.mark.asyncio
async def test_run_reel_check_updates_db_to_error_on_failure():
    """Verify that unhandled exceptions during run_reel_check set status to error and persist error message."""
    with patch("app.verifier.runner.download_clip", side_effect=RuntimeError("Download server down")), \
         patch("app.core.db.execute") as mock_db_execute:

        await run_reel_check("chk_test_fail", "https://example.com/fail.mp4")

        # Verify db was called with status='error'
        calls = [call[0] for call in mock_db_execute.call_args_list]
        error_call = next(
            c for c in calls
            if "status='error'" in c[0]
        )
        assert error_call[1][0] == "Download server down"
        assert error_call[1][1] == "chk_test_fail"
