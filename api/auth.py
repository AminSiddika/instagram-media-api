"""AES-encrypted API key authentication.

API keys are encrypted JSON payloads containing a key ID, role, and expiry.
Each issued key is encrypted with AES-256-CBC using a random IV (auto-generated
per request) and authenticated with HMAC-SHA256.

A static `MASTER_API_KEY` can be set in the environment. It bypasses expiry
and grants full admin access.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from api.config import Settings


class AuthError(Exception):
    """Base class for authentication failures."""

    pass


class InvalidKeyError(AuthError):
    """Raised when an API key cannot be decrypted or verified."""

    pass


class ExpiredKeyError(AuthError):
    """Raised when a valid API key has expired."""

    pass


def _decode_key(key_b64: Optional[str]) -> Optional[bytes]:
    """Decode a base64-encoded key."""
    if not key_b64:
        return None
    try:
        return base64.b64decode(key_b64)
    except Exception as exc:
        raise AuthError(f"Invalid base64 key: {exc}") from exc


def _derive_hmac_key(aes_key: bytes) -> bytes:
    """Derive a separate HMAC key from the AES key."""
    return hashlib.sha256(aes_key + b"hmac-salt").digest()


def _pad(data: bytes) -> bytes:
    """Apply PKCS7 padding."""
    pad_len = 16 - (len(data) % 16)
    return data + bytes([pad_len]) * pad_len


def _unpad(data: bytes) -> bytes:
    """Remove PKCS7 padding."""
    pad_len = data[-1]
    if pad_len > 16 or pad_len == 0:
        raise ValueError("Invalid padding")
    return data[:-pad_len]


def encrypt_payload(payload: dict, aes_key: bytes, iv: Optional[bytes] = None) -> str:
    """Encrypt a JSON payload with AES-256-CBC + HMAC-SHA256.

    Returns a URL-safe base64 token containing: iv + ciphertext + mac.
    """
    iv = iv or os.urandom(16)
    data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    cipher = Cipher(
        algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend()
    )
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(_pad(data)) + encryptor.finalize()

    mac_key = _derive_hmac_key(aes_key)
    mac = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()

    return base64.urlsafe_b64encode(iv + ciphertext + mac).decode().rstrip("=")


def decrypt_token(token: str, aes_key: bytes) -> dict:
    """Decrypt and verify an API key token."""
    try:
        # Add padding if needed
        token += "=" * (-len(token) % 4)
        raw = base64.urlsafe_b64decode(token)
    except Exception as exc:
        raise InvalidKeyError("Malformed API key") from exc

    if len(raw) < 48:  # 16 IV + at least 1 block + 32 HMAC
        raise InvalidKeyError("API key too short")

    iv = raw[:16]
    mac = raw[-32:]
    ciphertext = raw[16:-32]

    mac_key = _derive_hmac_key(aes_key)
    expected_mac = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected_mac):
        raise InvalidKeyError("Invalid API key signature")

    try:
        cipher = Cipher(
            algorithms.AES(aes_key), modes.CBC(iv), backend=default_backend()
        )
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        data = _unpad(padded)
        return json.loads(data.decode())
    except Exception as exc:
        raise InvalidKeyError(f"Could not decrypt API key: {exc}") from exc


def validate_api_key(token: Optional[str], settings: Settings) -> dict:
    """Validate an API key.

    Returns the decrypted payload if valid. The master key is checked first
    and never expires.
    """
    if not token:
        raise InvalidKeyError("API key is missing")

    if settings.master_api_key and token == settings.master_api_key:
        return {
            "kid": "master",
            "role": "admin",
            "exp": None,
            "type": "master",
        }

    aes_key = _decode_key(settings.aes_key)
    if not aes_key:
        raise AuthError("AES key is not configured")
    if len(aes_key) not in (16, 24, 32):
        raise AuthError("AES key must be 16, 24, or 32 bytes (base64 encoded)")

    payload = decrypt_token(token, aes_key)
    exp = payload.get("exp")
    if exp is not None and int(time.time()) > exp:
        raise ExpiredKeyError("API key has expired")

    return payload


def issue_api_key(
    settings: Settings,
    role: str = "user",
    ttl_hours: int = 24,
    key_id: Optional[str] = None,
) -> str:
    """Issue a new encrypted API key with an expiry.

    A random IV is generated automatically for each issued key.
    """
    aes_key = _decode_key(settings.aes_key)
    if not aes_key:
        raise AuthError("AES key is not configured")
    if len(aes_key) not in (16, 24, 32):
        raise AuthError("AES key must be 16, 24, or 32 bytes (base64 encoded)")

    kid = key_id or f"usr_{secrets.token_urlsafe(8)}"
    exp = int(
        (datetime.now(timezone.utc) + timedelta(hours=ttl_hours)).timestamp()
    )
    payload = {"kid": kid, "role": role, "exp": exp, "type": "issued"}
    return encrypt_payload(payload, aes_key)


def generate_aes_key() -> str:
    """Generate a new 256-bit AES key encoded as base64."""
    return base64.b64encode(os.urandom(32)).decode()
