"""
URL Security & SSRF Defense Boundary module.

Implements strict validation and defensive checks for all untrusted URL ingestion:
- Permitted schemes: only 'http' and 'https'
- Disallows userinfo / embedded credentials (e.g., http://user:pass@host)
- Disallows empty, malformed, or oversized hosts (>255 chars)
- Disallows IP addresses and hostnames resolving to:
  - Loopback (127.0.0.0/8, ::1)
  - Private networks (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, fc00::/7)
  - Link-local (169.254.0.0/16, fe80::/10)
  - Cloud metadata endpoints (169.254.169.254, metadata.google.internal, instance-data)
  - Multicast (224.0.0.0/4, ff00::/8)
  - Reserved / unspecified / broadcast (0.0.0.0/8, 240.0.0.0/4, 255.255.255.255, ::)
- Supports optional pre-download DNS resolution check to catch DNS-based private IP targeting.

NOTE ON REMAINING LIMITATION:
Because yt-dlp executes in a separate subprocess and performs its own HTTP requests, redirects,
and connection pooling, pre-resolution cannot completely prevent Time-of-Check to Time-of-Use
(TOCTOU) DNS rebinding or subsequent redirects to private targets unless yt-dlp itself enforces
an IP filter or proxy. This module provides defense-in-depth at both the schema/API boundary
and immediately before yt-dlp execution.
"""
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

MAX_URL_LENGTH = 2000
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
}


class URLValidationError(ValueError):
    """Raised when a URL fails security or format validation."""
    pass


def _is_ip_disallowed(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Returns True if the IP address belongs to private, loopback, link-local, or reserved ranges."""
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_url_security(url: str, resolve_dns: bool = False) -> str:
    """
    Validates a URL against strict security criteria:
    1. Length limit (<= 2000 chars)
    2. Explicit http/https scheme only
    3. Host presence and no embedded userinfo/credentials
    4. Prohibits IP literals and hostnames in loopback, private, link-local, multicast, or metadata ranges
    5. Optionally resolves hostname and validates resolved IP addresses.

    Returns the cleaned, validated URL string, or raises URLValidationError.
    """
    cleaned = url.strip()
    if not cleaned:
        raise URLValidationError("URL cannot be empty")

    if len(cleaned) > MAX_URL_LENGTH:
        raise URLValidationError(f"URL exceeds maximum length of {MAX_URL_LENGTH} characters")

    try:
        parsed = urlparse(cleaned)
    except Exception as e:
        raise URLValidationError(f"Malformed URL: {e}") from e

    # 1. Scheme check
    if parsed.scheme.lower() not in ("http", "https"):
        raise URLValidationError(f"Unsupported URL scheme: {parsed.scheme!r}. Only http and https are permitted.")

    # 2. Host presence check
    hostname = parsed.hostname
    if not hostname:
        raise URLValidationError("URL is missing a valid hostname")

    # 3. Disallow credentials / userinfo
    if parsed.username or parsed.password:
        raise URLValidationError("URLs containing embedded credentials are not permitted")

    # 4. Hostname format & blacklisted names
    lower_host = hostname.lower()
    if lower_host in BLOCKED_HOSTNAMES:
        raise URLValidationError(f"Destination host is not permitted: {hostname}")

    # Check for direct IP literal in hostname
    clean_ip_str = lower_host.strip("[]")
    try:
        ip_obj = ipaddress.ip_address(clean_ip_str)
    except ValueError:
        # Not a raw IP literal, it is a named host
        ip_obj = None

    if ip_obj is not None and _is_ip_disallowed(ip_obj):
        raise URLValidationError(f"Destination IP address {clean_ip_str} is in a restricted network range")


    # 5. Optional DNS resolution check
    if resolve_dns:
        try:
            addr_info = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if _is_ip_disallowed(ip_obj):
                    raise URLValidationError(
                        f"Destination host {hostname} resolved to restricted IP address {ip_str}"
                    )
        except socket.gaierror as e:
            raise URLValidationError(f"Could not resolve destination host {hostname}: {e}") from e

    return cleaned
