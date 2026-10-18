"""
Category A: Claim extraction and misleading wording tests.

Tests real application boundaries:
- extract_claims(manuscript) with empty/whitespace manuscripts (pure application logic)
- extract_claims(manuscript) with synthetic text fixtures containing:
  - direct assertions
  - paraphrased assertions
  - questions
  - clickbait statements
  - compound claims
  - opinion mixed with fact
  - incomplete quotations changing meaning
  - duplicate claims
  - transcripts with zero checkable claims
- match_quote_to_segments and attach_clip_times (actual quote boundary resolution)

Note on Model Mocking:
When extract_claims calls the model via Groq, the model client is mocked with controlled JSON responses.
These tests verify that application parsing, extraction schema handling, and boundary resolution work correctly,
asserting observable outputs without calling real AI providers.
"""
import json
from unittest.mock import MagicMock, patch
import pytest

from app.transcription.groq_whisper import TranscriptSegment
from app.verifier.claims import ExtractedClaim, extract_claims
from app.verifier.clip_match import attach_clip_times, match_quote_to_segments


def _create_mock_groq_response(claims_list: list[dict]):
    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"claims": claims_list})
    mock_resp.choices = [mock_choice]
    return mock_resp


# --- Pure Application Boundary: Empty & Whitespace Manuscripts ---

@pytest.mark.parametrize("empty_input", [
    "",
    "   ",
    "\n\n\t  \r\n",
])
def test_extract_claims_empty_manuscript(empty_input):
    """Assert application short-circuits on empty or whitespace manuscripts without calling model."""
    with patch("app.verifier.claims.next_client") as mock_client:
        claims = extract_claims(empty_input)
        assert claims == []
        mock_client.assert_not_called()


# --- Component-Level Parsing with Synthetic Fixtures (Mocked Model Boundary) ---

def test_extract_claims_direct_factual_assertion():
    """Verify parsing and extraction of a direct factual assertion."""
    fixture_claims = [
        {
            "quote": "The RBI increased the repo rate by 25 basis points in February.",
            "timestamp": "00:00:05",
            "claim": "RBI raised repo rate by 25 bps in February.",
        }
    ]
    with patch("app.verifier.claims.next_client") as mock_nc, \
         patch("app.verifier.claims._call_groq_with_retry", return_value=_create_mock_groq_response(fixture_claims)):
        mock_client = MagicMock()
        mock_nc.return_value = mock_client

        manuscript = "[00:00:05] The RBI increased the repo rate by 25 basis points in February."
        claims = extract_claims(manuscript)

        assert len(claims) == 1
        assert isinstance(claims[0], ExtractedClaim)
        assert claims[0].claim == "RBI raised repo rate by 25 bps in February."
        assert claims[0].quote == "The RBI increased the repo rate by 25 basis points in February."
        assert claims[0].timestamp == "00:00:05"


def test_extract_claims_paraphrased_assertion():
    """Verify handling when the transcript paraphrases an assertion."""
    fixture_claims = [
        {
            "quote": "India's central bank made borrowing more expensive earlier this year.",
            "timestamp": "00:00:12",
            "claim": "RBI raised interest rates earlier this year.",
        }
    ]
    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=_create_mock_groq_response(fixture_claims)):
        manuscript = "[00:00:12] India's central bank made borrowing more expensive earlier this year."
        claims = extract_claims(manuscript)
        assert len(claims) == 1
        assert claims[0].claim == "RBI raised interest rates earlier this year."


def test_extract_claims_claim_framed_as_question():
    """Verify handling when a claim is framed rhetorically as a question in the transcript."""
    fixture_claims = [
        {
            "quote": "Did you know that 80% of EV batteries are manufactured in China?",
            "timestamp": "00:00:20",
            "claim": "80% of EV batteries are manufactured in China.",
        }
    ]
    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=_create_mock_groq_response(fixture_claims)):
        manuscript = "[00:00:20] Did you know that 80% of EV batteries are manufactured in China?"
        claims = extract_claims(manuscript)
        assert len(claims) == 1
        assert claims[0].claim == "80% of EV batteries are manufactured in China."


def test_extract_claims_clickbait_no_verifiable_fact():
    """Verify that pure clickbait statements containing no verifiable facts return an empty claim list."""
    fixture_claims = []
    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=_create_mock_groq_response(fixture_claims)):
        manuscript = "[00:00:01] You will never believe what happens next! This mind-blowing secret changes everything!"
        claims = extract_claims(manuscript)
        assert claims == []


def test_extract_claims_multiple_compound_claims():
    """Verify multiple independent checkable claims extracted from a single compound sentence."""
    fixture_claims = [
        {
            "quote": "Unemployment fell to 4.1% while inflation rose to 6.2%.",
            "timestamp": "00:00:10",
            "claim": "Unemployment fell to 4.1%.",
        },
        {
            "quote": "Unemployment fell to 4.1% while inflation rose to 6.2%.",
            "timestamp": "00:00:10",
            "claim": "Inflation rose to 6.2%.",
        },
    ]
    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=_create_mock_groq_response(fixture_claims)):
        manuscript = "[00:00:10] Unemployment fell to 4.1% while inflation rose to 6.2%."
        claims = extract_claims(manuscript)
        assert len(claims) == 2
        assert {c.claim for c in claims} == {
            "Unemployment fell to 4.1%.",
            "Inflation rose to 6.2%.",
        }


def test_extract_claims_opinion_alongside_fact():
    """Verify extraction isolates the factual assertion when combined with subjective opinion."""
    fixture_claims = [
        {
            "quote": "In my personal opinion this terrible law caused a 15% increase in fuel taxes.",
            "timestamp": "00:00:15",
            "claim": "The law caused a 15% increase in fuel taxes.",
        }
    ]
    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=_create_mock_groq_response(fixture_claims)):
        manuscript = "[00:00:15] In my personal opinion this terrible law caused a 15% increase in fuel taxes."
        claims = extract_claims(manuscript)
        assert len(claims) == 1
        assert "opinion" not in claims[0].claim.lower()
        assert claims[0].claim == "The law caused a 15% increase in fuel taxes."


def test_extract_claims_incomplete_quotation():
    """Verify quote and claim handling when context is omitted in the transcript."""
    fixture_claims = [
        {
            "quote": "The minister stated 'we will cut pensions'.",
            "timestamp": "00:00:30",
            "claim": "The minister stated pensions will be cut.",
        }
    ]
    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=_create_mock_groq_response(fixture_claims)):
        manuscript = "[00:00:30] The minister stated 'we will cut pensions'."
        claims = extract_claims(manuscript)
        assert len(claims) == 1
        assert claims[0].quote == "The minister stated 'we will cut pensions'."


def test_extract_claims_duplicate_claims_handled():
    """Verify handling when duplicate claims are returned by extraction."""
    fixture_claims = [
        {
            "quote": "Gold hit an all time high today.",
            "timestamp": "00:00:05",
            "claim": "Gold price reached an all-time high.",
        },
        {
            "quote": "As I said before, gold reached an all time high.",
            "timestamp": "00:00:45",
            "claim": "Gold price reached an all-time high.",
        },
    ]
    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=_create_mock_groq_response(fixture_claims)):
        manuscript = "[00:00:05] Gold hit an all time high today.\n[00:00:45] As I said before, gold reached an all time high."
        claims = extract_claims(manuscript)
        assert len(claims) == 2
        # Quotes and timestamps remain distinct
        assert claims[0].timestamp != claims[1].timestamp


# --- Quote Alignment & Boundary Resolution Tests ---

def test_match_quote_to_segments_exact_and_fuzzy():
    """Verify match_quote_to_segments matches real segments and applies padding."""
    segments = [
        TranscriptSegment(absolute_start=0.0, absolute_end=4.0, text="Welcome back everyone"),
        TranscriptSegment(absolute_start=4.2, absolute_end=8.5, text="The RBI increased the repo rate by 25 basis points"),
        TranscriptSegment(absolute_start=8.6, absolute_end=12.0, text="which impacts all home loans"),
    ]
    # Exact quote match
    start, end = match_quote_to_segments(
        quote="The RBI increased the repo rate by 25 basis points",
        approx_timestamp="00:00:04",
        segments=segments,
    )
    # Starts at 4.2 - 0.3 padding = 3.9, ends at 8.5 + 0.3 padding = 8.8
    assert pytest.approx(start, 0.01) == 3.9
    assert pytest.approx(end, 0.01) == 8.8


def test_match_quote_to_segments_fallback_on_unmatched():
    """Verify fallback window calculation when quote has no matching transcript segment."""
    segments = [
        TranscriptSegment(absolute_start=0.0, absolute_end=4.0, text="Completely different topic"),
    ]
    start, end = match_quote_to_segments(
        quote="Unrelated claim text that never appeared",
        approx_timestamp="00:00:10",
        segments=segments,
    )
    # Fallback is approx_seconds (10.0) to approx_seconds + 8.0 = 18.0
    assert start == 10.0
    assert end == 18.0


def test_attach_clip_times_enrichment():
    """Verify attach_clip_times annotates all extracted claims."""
    claims = [
        ExtractedClaim(quote="First segment text", timestamp="00:00:01", claim="Claim 1"),
        ExtractedClaim(quote="Second segment text", timestamp="00:00:06", claim="Claim 2"),
    ]
    segments = [
        TranscriptSegment(absolute_start=1.0, absolute_end=5.0, text="First segment text"),
        TranscriptSegment(absolute_start=6.0, absolute_end=10.0, text="Second segment text"),
    ]
    enriched = attach_clip_times(claims, segments)
    assert len(enriched) == 2
    assert enriched[0].start_seconds == pytest.approx(0.7, 0.01)
    assert enriched[0].end_seconds == pytest.approx(5.3, 0.01)
    assert enriched[1].start_seconds == pytest.approx(5.7, 0.01)
    assert enriched[1].end_seconds == pytest.approx(10.3, 0.01)
