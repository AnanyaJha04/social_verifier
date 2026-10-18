"""
Category D: URL and network-input security tests.

Tests application URL ingestion boundaries:
1. Pydantic request models:
   - CreateReelCheckRequest (app/models/schemas.py)
   - CreateSessionRequest (app/models/schemas.py)
   - CreateBatchRequest (app/models/schemas.py)
2. FastAPI verify endpoint POST /api/verify with async_client
3. Download boundary: download_clip() in app/verifier/download.py

Test Cases:
- Unsupported schemes: ftp://, file://, gopher://, javascript:, data:
- Malformed URLs (spaces, no protocol, invalid characters, excessive length > 2000 chars)
- URLs containing embedded credentials (e.g. https://user:pass@example.com)
- Localhost, loopback, and private IPv4/IPv6 destinations (testing actual schema validation boundaries)
- Subprocess execution verification (ensuring yt-dlp receives safe argument lists, avoiding shell injection)
- yt-dlp download failure, missing output file, and missing audio track handling

SECURITY NOTE:
Application enforces:
- len(value) <= 2000
- value.startswith(("http://", "https://"))
It does NOT perform DNS resolution, private IP blocklisting (SSRF filtering), or redirect checking.
Tests verify what is actually implemented and assert the exact observed behavior.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from pydantic import ValidationError

from app.models.schemas import CreateBatchRequest, CreateReelCheckRequest, CreateSessionRequest
from app.verifier.download import DownloadError, download_clip


# --- Schema Level Validation ---

@pytest.mark.parametrize("invalid_url", [
    "ftp://example.com/video.mp4",
    "file:///etc/passwd",
    "file://c:/windows/system32",
    "javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "not_a_url",
    "//example.com/video",
    "",
    "   ",
])
def test_schema_rejects_unsupported_schemes(invalid_url):
    """Verify Pydantic models reject non-http(s) schemes with ValueError/ValidationError."""
    with pytest.raises(ValidationError):
        CreateReelCheckRequest(url=invalid_url)

    with pytest.raises(ValidationError):
        CreateSessionRequest(url=invalid_url)


def test_schema_rejects_excessive_url_length():
    """Verify rejection of URLs exceeding 2000 characters."""
    oversized_url = "https://example.com/" + "a" * 2000
    with pytest.raises(ValidationError):
        CreateReelCheckRequest(url=oversized_url)


@pytest.mark.parametrize("url_with_credentials", [
    "https://admin:secret123@example.com/video.mp4",
    "http://user:password@internal-server.local/stream",
])
def test_schema_accepts_url_with_credentials_at_pydantic_level(url_with_credentials):
    """
    Verify URLs with userinfo/embedded credentials are now strictly rejected by schema validation.
    """
    with pytest.raises(ValidationError) as exc_info:
        CreateReelCheckRequest(url=url_with_credentials)
    assert "embedded credentials" in str(exc_info.value)


@pytest.mark.parametrize("private_destination", [
    "http://127.0.0.1:8000/internal",
    "http://localhost:5000/admin",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/status",
    "http://192.168.1.1/router",
    "http://[::1]:8080/metrics",
    "http://[fe80::1]/service",
    "http://0.0.0.0/test",
])
def test_private_and_loopback_urls_rejected_by_validation(private_destination):
    """
    Verify that loopback, private IP, and cloud metadata targets are rejected by schema validation.
    """
    with pytest.raises(ValidationError):
        CreateReelCheckRequest(url=private_destination)


def test_download_clip_enforces_url_security_and_dns_rejection(tmp_path):
    """
    Verify download_clip validates URL and rejects private destinations before calling yt-dlp.
    """
    dest = tmp_path / "clip"
    with patch("app.core.url_security.socket.getaddrinfo") as mock_dns:
        # Simulate hostname resolving to loopback IP
        mock_dns.return_value = [(2, 1, 6, "", ("127.0.0.1", 80))]
        with pytest.raises(DownloadError) as exc_info:
            download_clip("http://attacker-controlled-rebind.com/video.mp4", dest)
        assert "restricted IP address" in str(exc_info.value)



def test_create_batch_empty_urls_rejected():
    """Verify CreateBatchRequest rejects non-http(s) or empty URL items in the list."""
    with pytest.raises(ValidationError):
        CreateBatchRequest(urls=["  ", ""])


# --- Subprocess & Download Boundaries ---

def test_download_clip_subprocess_arg_safety(tmp_path):
    """
    Verify yt-dlp is invoked as an argument list (no shell=True), preventing command injection.
    """
    dest_dir = tmp_path / "dest"
    malicious_url = "https://example.com/video.mp4; touch /tmp/pwned"

    with patch("app.verifier.download.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="yt-dlp error")

        with pytest.raises(DownloadError):
            download_clip(malicious_url, dest_dir)

        # Assert cmd passed to subprocess.run is a list and contains malicious_url as a single token
        called_cmd = mock_run.call_args[0][0]
        assert isinstance(called_cmd, list)
        assert malicious_url in called_cmd
        # Ensure --no-playlist is present
        assert "--no-playlist" in called_cmd


def test_download_clip_handles_process_failure(tmp_path):
    """Verify download_clip raises DownloadError when yt-dlp exits non-zero."""
    dest_dir = tmp_path / "dest"
    with patch("app.verifier.download.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=2, stderr="ERROR: Unsupported URL")
        with pytest.raises(DownloadError) as exc_info:
            download_clip("https://example.com/unsupported", dest_dir)
        assert "yt-dlp failed to download" in str(exc_info.value)
        assert "Unsupported URL" in str(exc_info.value)


def test_download_clip_handles_missing_output_file(tmp_path):
    """Verify download_clip raises DownloadError if yt-dlp reports success but creates no file."""
    dest_dir = tmp_path / "dest"
    with patch("app.verifier.download.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with pytest.raises(DownloadError) as exc_info:
            download_clip("https://example.com/nofile", dest_dir)
        assert "produced no file" in str(exc_info.value)


def test_download_clip_handles_video_without_audio_stream(tmp_path):
    """Verify download_clip detects video-only files without audio streams and raises clear DownloadError."""
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir(parents=True, exist_ok=True)
    fake_video = dest_dir / "source.mp4"
    fake_video.write_bytes(b"mock video data")

    with patch("app.verifier.download.subprocess.run") as mock_run, \
         patch("app.verifier.download._has_audio_stream", return_value=False):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        with pytest.raises(DownloadError) as exc_info:
            download_clip("https://example.com/video_no_audio", dest_dir)
        assert "has no audio track" in str(exc_info.value)


# --- API Endpoint HTTP Boundary ---

@pytest.mark.asyncio
async def test_api_create_reel_check_rejects_invalid_url(async_client):
    """Verify FastAPI endpoint returns 422 Unprocessable Entity for invalid scheme when authenticated."""
    from app.core.auth import SESSION_TOKEN
    headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
    response = await async_client.post("/api/verify", json={"url": "ftp://bad-scheme.com"}, headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_create_batch_rejects_empty_urls_when_authenticated(async_client):
    """Verify POST /api/verify/batch returns 422 for invalid/empty URL lists at schema boundary."""
    from app.core.auth import SESSION_TOKEN
    headers = {"Authorization": f"Bearer {SESSION_TOKEN}"}
    response = await async_client.post("/api/verify/batch", json={"urls": ["", "   "]}, headers=headers)
    assert response.status_code == 422
