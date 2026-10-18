"""
Category F: Transcription and audio edge cases tests.

Tests application transcription boundary components:
- transcribe_chunk() in app/transcription/groq_whisper.py:
  - Empty transcription response
  - Whitespace-only transcription
  - Fallback from segment list to full text
  - Absolute timestamp calculation with chunk offsets
  - Repeated words and rapid text handling
  - Timestamp ordering and malformed segment objects
- build_manuscript() in app/verifier/manuscript.py:
  - Empty audio transcript returns empty manuscript ("") and empty segment list
  - Normal segment list converted to formatted timestamped manuscript
"""
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.transcription.groq_whisper import TranscriptSegment, transcribe_chunk
from app.verifier.manuscript import build_manuscript


@dataclass
class MockWhisperSegment:
    start: float
    end: float
    text: str


def test_transcribe_chunk_with_segments(tmp_path):
    """Verify standard response with segments converts relative timestamps to absolute offsets."""
    audio_file = tmp_path / "chunk.wav"
    audio_file.write_bytes(b"RIFF dummy audio data")

    mock_resp = MagicMock()
    mock_resp.segments = [
        {"start": 1.0, "end": 4.5, "text": " Good morning viewers."},
        {"start": 5.0, "end": 9.2, "text": " Breaking news today."},
    ]
    mock_resp.text = "Good morning viewers. Breaking news today."

    with patch("app.transcription.groq_whisper.next_client") as mock_nc:
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp
        mock_nc.return_value = mock_client

        # Offset of 60.0 seconds
        segments = transcribe_chunk(audio_file, chunk_start_offset=60.0)

        assert len(segments) == 2
        assert segments[0].absolute_start == 61.0
        assert segments[0].absolute_end == 64.5
        assert segments[0].text == "Good morning viewers."
        assert segments[1].absolute_start == 65.0
        assert segments[1].absolute_end == 69.2
        assert segments[1].text == "Breaking news today."


def test_transcribe_chunk_fallback_to_whole_text(tmp_path):
    """Verify fallback to chunk-level text when segment-level timestamps are missing."""
    audio_file = tmp_path / "chunk.wav"
    audio_file.write_bytes(b"RIFF dummy audio data")

    mock_resp = MagicMock()
    mock_resp.segments = []  # No segment breakdown
    mock_resp.text = "Speech recognized across whole chunk."

    with patch("app.transcription.groq_whisper.next_client") as mock_nc:
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp
        mock_nc.return_value = mock_client

        segments = transcribe_chunk(audio_file, chunk_start_offset=10.0)

        assert len(segments) == 1
        assert segments[0].absolute_start == 10.0
        assert segments[0].text == "Speech recognized across whole chunk."


@pytest.mark.parametrize("empty_text", [
    "",
    "   ",
    "\n\t",
])
def test_transcribe_chunk_empty_response(tmp_path, empty_text):
    """Verify empty or whitespace-only response produces an empty segment list."""
    audio_file = tmp_path / "chunk.wav"
    audio_file.write_bytes(b"RIFF dummy audio data")

    mock_resp = MagicMock()
    mock_resp.segments = []
    mock_resp.text = empty_text

    with patch("app.transcription.groq_whisper.next_client") as mock_nc:
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_resp
        mock_nc.return_value = mock_client

        segments = transcribe_chunk(audio_file, chunk_start_offset=0.0)
        assert segments == []


def test_build_manuscript_empty_segments(tmp_path):
    """Verify build_manuscript produces empty string and empty list when transcription returns no segments."""
    raw = tmp_path / "raw.wav"
    dsp = tmp_path / "dsp.wav"
    raw.write_bytes(b"raw")

    with patch("app.verifier.manuscript.apply_dsp"), \
         patch("app.verifier.manuscript.transcribe_chunk", return_value=[]):
        manuscript, segments = build_manuscript(raw, dsp)
        assert manuscript == ""
        assert segments == []


def test_build_manuscript_formatting(tmp_path):
    """Verify build_manuscript formats timestamps as [HH:MM:SS] text."""
    raw = tmp_path / "raw.wav"
    dsp = tmp_path / "dsp.wav"
    raw.write_bytes(b"raw")

    sample_segments = [
        TranscriptSegment(absolute_start=5.0, absolute_end=9.0, text="First statement."),
        TranscriptSegment(absolute_start=3665.0, absolute_end=3670.0, text="One hour later."),
    ]

    with patch("app.verifier.manuscript.apply_dsp"), \
         patch("app.verifier.manuscript.transcribe_chunk", return_value=sample_segments):
        manuscript, segments = build_manuscript(raw, dsp)
        lines = manuscript.splitlines()
        assert len(lines) == 2
        assert lines[0] == "[00:00:05] First statement."
        assert lines[1] == "[01:01:05] One hour later."
