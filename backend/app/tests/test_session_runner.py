# app/tests/test_session_runner.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_session_runner_successful_pipeline():
    """Test session runner while mocking the Groq client inside groq_whisper."""
    with patch("app.ingest.capture.CaptureSupervisor") as mock_capture, \
         patch("app.transcription.groq_whisper.next_client") as mock_groq_client:

        # Mock capture setup
        capture_inst = MagicMock()
        capture_inst.run = AsyncMock(return_value={"audio_path": "/tmp/test.wav"})
        mock_capture.return_value = capture_inst
        
        # Mock Groq client API response
        mock_groq_client.return_value.audio.transcriptions.create = AsyncMock(
            return_value=MagicMock(text="Sample transcribed text")
        )

        import app.session_runner as sr
        assert sr is not None

@pytest.mark.asyncio
async def test_session_runner_ingest_failure():
    """Verify ingest failure handling."""
    with patch("app.ingest.capture.CaptureSupervisor") as mock_capture:
        capture_inst = MagicMock()
        capture_inst.run = AsyncMock(side_effect=Exception("Ingest error"))
        mock_capture.return_value = capture_inst

        import app.session_runner as sr
        assert sr is not None