"""Security helpers: rate limiting, abuse logging, and request sanitization."""

import hashlib
import ipaddress
import logging
import time
from collections import defaultdict
from typing import Dict, List, Optional

from fastapi import HTTPException, Request, Response

from api.auth import AuthError, issue_api_key, validate_api_key
from api.config import Settings

logger = logging.getLogger(__name__)

# In-memory rate limit buckets per API key. In a multi-server setup, replace with Redis.
_request_buckets: Dict[str, List[float]] = defaultdict(list)
_failed_auth_buckets: Dict[str, List[float]] = defaultdict(list)


class KeyRevocationStore:
    """In-memory store of used single-use key IDs with TTL cleanup.

    NOTE: This is per-instance memory. For a multi-server/serverless setup,
    replace with Redis or a shared cache.
    """

    def __init__(self, ttl_seconds: int = 3600):
        self._used: Dict[str, float] = {}
        self._ttl = ttl_seconds

    def mark_used(self, key_id: str) -> None:
        self._cleanup()
        self._used[key_id] = time.time()

    def is_used(self, key_id: str) -> bool:
        self._cleanup()
        return key_id in self._used

    def revoked_ids(self) -> set:
        self._cleanup()
        return set(self._used.keys())

    def clear(self) -> None:
        self._used.clear()

    def _cleanup(self) -> None:
        now = time.time()
        expired = [k for k, v in self._used.items() if now - v > self._ttl]
        for k in expired:
            del self._used[k]


# Global revocation store for single-use keys
_revocation_store = KeyRevocationStore()


def get_revocation_store() -> KeyRevocationStore:
    """Return the global key revocation store (useful for tests)."""
    return _revocation_store


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


def _get_bucket_key(api_key: Optional[str], request: Request) -> str:
    """Build a rate limit bucket key from key fingerprint + IP."""
    return f"{_sanitize_key(api_key)}:{_get_client_ip(request)}"


def check_rate_limit(api_key: Optional[str], request: Request, settings: Settings) -> None:
    """Enforce a simple per-key/IP sliding window rate limit."""
    limit = settings.rate_limit_requests
    window = settings.rate_limit_window_seconds
    if limit <= 0:
        return

    bucket_key = _get_bucket_key(api_key, request)
    now = time.time()
    cutoff = now - window

    # Keep only requests within the window
    bucket = [ts for ts in _request_buckets[bucket_key] if ts > cutoff]
    bucket.append(now)
    _request_buckets[bucket_key] = bucket

    if len(bucket) > limit:
        logger.warning(
            "Rate limit exceeded",
            extra={
                "key_fp": _sanitize_key(api_key),
                "ip": _get_client_ip(request),
                "count": len(bucket),
            },
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please slow down.",
        )


def record_failed_auth(api_key: Optional[str], request: Request, settings: Settings) -> None:
    """Record a failed authentication attempt and block repeat abusers."""
    max_attempts = settings.max_failed_auth_attempts
    window = settings.failed_auth_window_seconds
    if max_attempts <= 0:
        return

    ip = _get_client_ip(request)
    bucket_key = f"{_sanitize_key(api_key)}:{ip}" if api_key else f"ip:{ip}"
    now = time.time()
    cutoff = now - window

    bucket = [ts for ts in _failed_auth_buckets[bucket_key] if ts > cutoff]
    bucket.append(now)
    _failed_auth_buckets[bucket_key] = bucket

    logger.warning(
        "Failed auth attempt",
        extra={
            "key_fp": _sanitize_key(api_key),
            "ip": ip,
            "attempts": len(bucket),
        },
    )

    if len(bucket) >= max_attempts:
        logger.warning(
            "Too many failed auth attempts",
            extra={"key_fp": _sanitize_key(api_key), "ip": ip},
        )
        raise HTTPException(
            status_code=403,
            detail="Too many failed authentication attempts. Try again later.",
        )


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


def rotate_api_key(
    payload: dict,
    settings: Settings,
    response: Response,
) -> Optional[str]:
    """If the key is single-use, mark it used and issue a fresh key in the response header.

    Returns the new token if rotated, otherwise None.
    """
    if payload.get("type") == "master":
        return None
    if not payload.get("single_use", True):
        return None

    kid = payload.get("kid")
    role = payload.get("role", "user")
    if kid:
        _revocation_store.mark_used(kid)

    try:
        new_token = issue_api_key(
            settings,
            role=role,
            ttl_hours=settings.default_key_ttl_hours,
            single_use=True,
        )
        response.headers["X-New-API-Key"] = new_token
        return new_token
    except AuthError as exc:
        logger.error("Failed to rotate API key: %s", exc)
        return None


def validate_and_maybe_rotate(
    api_key: Optional[str],
    request: Request,
    response: Response,
    settings: Settings,
) -> dict:
    """Validate an API key, enforce rate limits, and rotate single-use keys."""
    check_rate_limit(api_key, request, settings)
    try:
        payload = validate_api_key(api_key, settings, revoked_kids=_revocation_store.revoked_ids())
        new_key = rotate_api_key(payload, settings, response)
        log_request(
            request,
            api_key,
            status="authenticated",
            extra={"rotated": new_key is not None, "kid": payload.get("kid")},
        )
        return payload
    except Exception as exc:
        # Re-raise specific exceptions after recording failed auth
        record_failed_auth(api_key, request, settings)
        raise
