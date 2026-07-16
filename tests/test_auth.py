"""Tests for the AES-encrypted API key authentication system."""

import base64
import os

import pytest

os.environ["AES_KEY"] = base64.b64encode(b"a" * 32).decode()
os.environ["MASTER_API_KEY"] = "test-master-key"
os.environ["RATE_LIMIT_REQUESTS"] = "10000"
os.environ["MAX_FAILED_AUTH_ATTEMPTS"] = "10000"

from api.auth import (
    AuthError,
    ExpiredKeyError,
    InvalidKeyError,
    generate_aes_key,
    issue_api_key,
    validate_api_key,
)
from api.config import Settings


@pytest.fixture
def settings():
    return Settings(
        aes_key=generate_aes_key(),
        master_api_key="master-static-key",
        default_key_ttl_hours=24,
    )


class TestKeyIssuance:
    def test_issue_and_validate_key(self, settings):
        token = issue_api_key(settings, role="user", ttl_hours=1)
        payload = validate_api_key(token, settings)
        assert payload["role"] == "user"
        assert payload["kid"].startswith("usr_")
        assert payload["type"] == "issued"
        assert payload["exp"] is not None
        assert payload.get("single_use", True) is True

    def test_issue_key_with_custom_id(self, settings):
        token = issue_api_key(settings, role="user", ttl_hours=1, key_id="abc123")
        payload = validate_api_key(token, settings)
        assert payload["kid"] == "abc123"

    def test_issued_key_expires(self, settings):
        token = issue_api_key(settings, role="user", ttl_hours=-1)
        with pytest.raises(ExpiredKeyError):
            validate_api_key(token, settings)

    def test_issue_non_single_use_key(self, settings):
        token = issue_api_key(settings, role="user", ttl_hours=1, single_use=False)
        payload = validate_api_key(token, settings)
        assert payload.get("single_use") is False


class TestMasterKey:
    def test_master_key_is_valid(self, settings):
        payload = validate_api_key("master-static-key", settings)
        assert payload["kid"] == "master"
        assert payload["role"] == "admin"
        assert payload["exp"] is None
        assert payload["type"] == "master"

    def test_invalid_master_key_rejected(self, settings):
        with pytest.raises(InvalidKeyError):
            validate_api_key("wrong-master-key", settings)


class TestInvalidKeys:
    def test_missing_key(self, settings):
        with pytest.raises(InvalidKeyError):
            validate_api_key(None, settings)

    def test_random_string_rejected(self, settings):
        with pytest.raises(InvalidKeyError):
            validate_api_key("not-a-valid-token", settings)

    def test_tampered_token_rejected(self, settings):
        token = issue_api_key(settings, role="user", ttl_hours=1)
        # Tamper with the ciphertext by flipping a character
        tampered = token[:-5] + ("X" if token[-5] != "X" else "Y") + token[-4:]
        with pytest.raises(InvalidKeyError):
            validate_api_key(tampered, settings)


class TestConfiguration:
    def test_missing_aes_key_raises(self):
        settings = Settings(aes_key="", master_api_key="")
        with pytest.raises(AuthError):
            validate_api_key("some-key", settings)

    def test_invalid_aes_key_length(self, settings):
        settings = Settings(aes_key=base64.b64encode(b"short").decode(), master_api_key="")
        with pytest.raises(AuthError):
            validate_api_key("some-key", settings)


class TestKeyGeneration:
    def test_generate_aes_key(self):
        key = generate_aes_key()
        raw = base64.b64decode(key)
        assert len(raw) == 32
