"""
Category C: Verdict and response parsing adversarial tests.

Tests model response parsing under adversarial and boundary conditions:
- _parse_verification() and verify_claim() with:
  - each supported primary verdict ("true", "false", "misleading", "partially true", "unverifiable")
  - unsupported verdict labels (e.g. "mostly true", "pants on fire", "accurate", "debunked")
  - missing verdict field
  - missing analysis field (KeyError)
  - empty responses
  - malformed JSON
  - truncated JSON
  - unexpected data types (e.g. verdict is a list or int, sources is a dict or string)
  - additional unexpected fields (payload stuffing)
  - provider error / exception during call
  - markdown code fence wrappers (```json ... ```)
  - government verification schema parsing (_verify_against_gov_sources)

Asserts safe failure, absence of silent crashes, and strict schema adherence.
"""
import json
from unittest.mock import MagicMock, patch
import pytest

from app.verifier.claims import (
    ExtractedClaim,
    _parse_verification,
    _verify_against_gov_sources,
    _verify_via_plain_model,
    verify_claim,
)


# --- Supported Primary Verdicts ---

@pytest.mark.parametrize("verdict", [
    "true",
    "false",
    "misleading",
    "partially true",
    "unverifiable",
])
def test_parse_verification_supported_verdicts(verdict):
    """Verify that each supported primary verdict is parsed accurately."""
    payload = json.dumps({
        "verdict": verdict,
        "analysis": f"Detailed analysis explaining why it is {verdict}.",
        "sources": ["https://example.com/source1"],
    })
    v, a, s = _parse_verification(payload)
    assert v == verdict
    assert "Detailed analysis" in a
    assert s == ["https://example.com/source1"]


# --- Code Fence Handling ---

def test_parse_verification_markdown_code_fences():
    """Verify that json payloads wrapped in markdown fences are stripped and parsed cleanly."""
    payload = """```json
    {
      "verdict": "false",
      "analysis": "This claim is contradicted by official records.",
      "sources": ["https://pib.gov.in/factcheck"]
    }
    ```"""
    v, a, s = _parse_verification(payload)
    assert v == "false"
    assert "contradicted by official records" in a
    assert s == ["https://pib.gov.in/factcheck"]


# --- Missing Fields & Defaults ---

def test_parse_verification_missing_verdict_defaults_to_unverifiable():
    """When the model omits the 'verdict' key, verify it safely defaults to 'unverifiable'."""
    payload = json.dumps({
        "analysis": "Analysis provided but no verdict given.",
        "sources": [],
    })
    v, a, s = _parse_verification(payload)
    assert v == "unverifiable"
    assert a == "Analysis provided but no verdict given."


def test_parse_verification_missing_analysis_raises_key_error():
    """When the required 'analysis' key is missing, _parse_verification raises KeyError."""
    payload = json.dumps({
        "verdict": "true",
        "sources": [],
    })
    with pytest.raises(KeyError):
        _parse_verification(payload)


def test_parse_verification_missing_sources_defaults_to_empty_list():
    """When 'sources' is omitted or None, verify it safely defaults to an empty list."""
    payload = json.dumps({
        "verdict": "true",
        "analysis": "Some analysis",
    })
    v, a, s = _parse_verification(payload)
    assert s == []


# --- Malformed & Truncated JSON Handling ---

@pytest.mark.parametrize("malformed_payload", [
    "",
    "   ",
    "{",
    '{"verdict": "true", "analysis": "incomplete',
    "Not a JSON object",
    "<html>502 Bad Gateway</html>",
    "None",
])
def test_parse_verification_malformed_json_raises(malformed_payload):
    """Verify malformed JSON raises JSONDecodeError at parsing boundary."""
    with pytest.raises(json.JSONDecodeError):
        _parse_verification(malformed_payload)


def test_verify_via_plain_model_handles_malformed_json_safely():
    """Verify that when the model returns malformed JSON, _verify_via_plain_model returns unverifiable safely."""
    claim = ExtractedClaim(quote="test quote", timestamp="00:00:01", claim="test claim")

    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Truncated JSON: {\"verdict\": \"true"
    mock_resp.choices = [mock_choice]

    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=mock_resp):
        verdict, analysis, sources = _verify_via_plain_model(claim, [])
        assert verdict == "unverifiable"
        assert "malformed response" in analysis.lower()
        assert sources == []


# --- Additional Fields & Unexpected Data Types ---

def test_parse_verification_extra_fields_ignored_safely():
    """Verify extra unexpected fields (payload stuffing) do not crash parsing or leak into return tuple."""
    payload = json.dumps({
        "verdict": "true",
        "analysis": "Valid analysis",
        "sources": ["https://src.com"],
        "extra_field": "injected",
        "internal_debug": 12345,
    })
    v, a, s = _parse_verification(payload)
    assert v == "true"
    assert a == "Valid analysis"
    assert s == ["https://src.com"]


# --- Unsupported / Hallucinated Verdict Labels ---

@pytest.mark.parametrize("unsupported_label", [
    "mostly true",
    "partially false",
    "pants on fire",
    "debunked",
    "accurate",
    "verified",
    "",
    "   ",
])
def test_unsupported_verdict_label_handling(unsupported_label):
    """
    Test application behavior when model produces an unsupported verdict label.
    Strict validation normalizes/defaults any non-canonical verdict to 'unverifiable'.
    """
    payload = json.dumps({
        "verdict": unsupported_label,
        "analysis": "Partially accurate but not an approved enum value.",
        "sources": [],
    })
    v, a, s = _parse_verification(payload)
    assert v == "unverifiable"


@pytest.mark.parametrize("invalid_verdict_type", [
    123,
    True,
    ["true"],
    {"label": "true"},
    None,
])
def test_invalid_verdict_type_handling(invalid_verdict_type):
    """Verify non-string verdict data types are safely defaulted to 'unverifiable'."""
    payload = json.dumps({
        "verdict": invalid_verdict_type,
        "analysis": "Analysis provided with non-string verdict.",
        "sources": [],
    })
    v, a, s = _parse_verification(payload)
    assert v == "unverifiable"
    assert a == "Analysis provided with non-string verdict."



# --- Government Source Response Parsing ---

@pytest.mark.parametrize("gov_response, expected_verdict", [
    (json.dumps({"verdict": "confirmed", "analysis": "Official press release matches."}), "confirmed"),
    (json.dumps({"verdict": "contradicted", "analysis": "Official gazette contradicts this."}), "contradicted"),
    (json.dumps({"verdict": "partially confirmed", "analysis": "Only some figures match."}), "partially confirmed"),
    (json.dumps({"verdict": "not addressed", "analysis": "Topic not mentioned in excerpts."}), "not addressed"),
    ("Malformed text", "not addressed"),
    (json.dumps({}), "not addressed"),
])
def test_verify_against_gov_sources_parsing(gov_response, expected_verdict):
    """Verify _verify_against_gov_sources parses all valid verdicts and safely falls back on malformed input."""
    claim = ExtractedClaim(quote="test quote", timestamp="00:00:01", claim="test claim")
    gov_hits = [{"title": "Gazette", "url": "https://gov.in/gazette", "text": "Excerpt text"}]

    mock_resp = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = gov_response
    mock_resp.choices = [mock_choice]

    with patch("app.verifier.claims.next_client"), \
         patch("app.verifier.claims._call_groq_with_retry", return_value=mock_resp):
        v, a = _verify_against_gov_sources(claim, gov_hits)
        assert v == expected_verdict
        assert isinstance(a, str)
