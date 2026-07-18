"""Security helpers: request logging and IP parsing."""

import hashlib
import ipaddress
import logging
from typing import Optional

from fastapi import Request

from api.config import Settings

logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, accounting for Vercel's proxy headers."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _sanitize_key(key: Optional[str]) -> str:
    """Return a safe hash/fingerprint of a key for logging without leaking it."""
    if not key:
        return "<missing>"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def log_request(
    request: Request,
    api_key: Optional[str] = None,
    status: str = "ok",
    extra: Optional[dict] = None,
) -> None:
    """Log a request with sanitized key info."""
    info = {
        "method": request.method,
        "path": request.url.path,
        "ip": _get_client_ip(request),
        "key_fp": _sanitize_key(api_key),
        "status": status,
    }
    if extra:
        info.update(extra)
    logger.info("Request", extra=info)


def is_private_ip(ip: str) -> bool:
    """Return True if the IP is a private/reserved address."""
    try:
        addr = ipaddress.ip_address(ip.split(":")[0])
        return addr.is_private or addr.is_loopback or addr.is_reserved
    except ValueError:
        return False

