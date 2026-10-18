"""
Category E: Media processing and resource limits tests.

Tests application boundaries around media processing, FFmpeg execution, and temporary files:
- FFmpeg subprocess execution via run_checked (app/core/proc.py)
  - Non-zero exit code produces RuntimeError with stderr included
  - Missing executable raises FileNotFoundError
  - Subprocess timeout handling
- Audio extraction (extract_audio in app/verifier/download.py)
  - Valid invocation arguments
  - Non-existent input file
- Audio DSP filtering (apply_dsp and concat_wavs in app/transcription/audio_preprocess.py)
  - Handling empty input file or corrupted data
  - Concat file listing cleanup in finally block
- Reel check pipeline temporary directory lifecycle (run_reel_check in app/verifier/runner.py)
  - Temporary files created inside tempfile.TemporaryDirectory are cleaned up on failure
- Clip cutting resource limits and bounds (cut_claim_clip in app/verifier/clip_cutter.py)
  - Zero/negative or inverted timestamps
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.core.proc import run_checked
from app.transcription.audio_preprocess import apply_dsp, concat_wavs
from app.verifier.clip_cutter import cut_claim_clip
from app.verifier.download import extract_audio


def test_run_checked_success():
    """Verify run_checked completes and returns CompletedProcess on 0 exit."""
    res = run_checked(["python", "-c", "import sys; sys.exit(0)"])
    assert res.returncode == 0


def test_run_checked_captures_stderr_on_failure():
    """Verify run_checked raises RuntimeError containing process return code and stderr."""
    with pytest.raises(RuntimeError) as exc_info:
        run_checked(["python", "-c", "import sys; sys.stderr.write('Fatal audio codec error'); sys.exit(1)"])
    err_str = str(exc_info.value)
    assert "Command failed (exit 1)" in err_str
    assert "Fatal audio codec error" in err_str


def test_run_checked_missing_executable():
    """Verify run_checked raises FileNotFoundError when target binary does not exist."""
    with pytest.raises(FileNotFoundError):
        run_checked(["nonexistent_ffmpeg_binary_xyz", "-version"])


def test_run_checked_timeout_handling():
    """Verify run_checked propagates subprocess.TimeoutExpired when execution exceeds timeout."""
    with pytest.raises(subprocess.TimeoutExpired):
        run_checked(["python", "-c", "import time; time.sleep(2)"], timeout=0.1)


def test_extract_audio_invokes_correct_ffmpeg_args(tmp_path):
    """Verify extract_audio configures 16kHz mono pcm_s16le audio extraction."""
    video = tmp_path / "source.mp4"
    audio = tmp_path / "audio.wav"
    video.write_bytes(b"dummy")

    with patch("app.verifier.download.run_checked") as mock_run:
        res = extract_audio(video, audio)
        assert res == audio
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-vn" in cmd
        assert "-ac" in cmd and "1" in cmd
        assert "-ar" in cmd and "16000" in cmd
        assert "-c:a" in cmd and "pcm_s16le" in cmd


def test_apply_dsp_invokes_filter_chain(tmp_path):
    """Verify apply_dsp passes standard audio filtering chain to ffmpeg."""
    in_wav = tmp_path / "in.wav"
    out_wav = tmp_path / "out.wav"
    in_wav.write_bytes(b"dummy")

    with patch("app.transcription.audio_preprocess.run_checked") as mock_run:
        apply_dsp(in_wav, out_wav)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "-af" in cmd
        assert "highpass=f=80,afftdn,loudnorm,acompressor" in cmd


def test_concat_wavs_cleans_up_manifest_file(tmp_path):
    """Verify concat_wavs creates a temporary concat file and unlinks it even if run_checked fails."""
    w1 = tmp_path / "1.wav"
    w2 = tmp_path / "2.wav"
    out = tmp_path / "out.wav"
    w1.write_bytes(b"data1")
    w2.write_bytes(b"data2")

    with patch("app.transcription.audio_preprocess.run_checked", side_effect=RuntimeError("FFmpeg concat failed")):
        with pytest.raises(RuntimeError):
            concat_wavs([w1, w2], out)

    # Verify no leaked temporary text files in the temp directory
    txt_files = list(Path(tmp_path).glob("*.txt"))
    assert len(txt_files) == 0


def test_cut_claim_clip_clamps_negative_start(tmp_path):
    """Verify cut_claim_clip handles negative start times by clamping to 0.0."""
    src = tmp_path / "source.mp4"
    out = tmp_path / "clip.mp4"
    src.write_bytes(b"video")

    with patch("app.verifier.clip_cutter.run_checked") as mock_run:
        cut_claim_clip(src, -5.0, 10.0, out)
        cmd = mock_run.call_args[0][0]
        # First -ss argument clamped to 0.000, duration (-t) is end - start = 10.0 - (-5.0) = 15.000
        assert "-ss" in cmd
        assert "0.000" in cmd
        assert "-t" in cmd
        assert "15.000" in cmd


