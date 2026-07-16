"""Integration tests for the FastAPI application."""

import base64
import os

import pytest
from fastapi.testclient import TestClient

# Set auth env vars before importing the app
os.environ["AES_KEY"] = base64.b64encode(b"a" * 32).decode()
os.environ["MASTER_API_KEY"] = "test-master-key"
os.environ["RATE_LIMIT_REQUESTS"] = "10000"
os.environ["RATE_LIMIT_WINDOW_SECONDS"] = "60"
os.environ["MAX_FAILED_AUTH_ATTEMPTS"] = "10000"
os.environ["FAILED_AUTH_WINDOW_SECONDS"] = "300"

from api.config import get_settings
from api.index import app


@pytest.fixture(autouse=True)
def reset_settings_cache():
    get_settings.cache_clear()


client = TestClient(app)


def test_root_landing_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "Instagram Media API" in response.text


def test_health_check():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


class TestAuthEndpoints:
    def test_issue_key_requires_master_key(self):
        response = client.post("/api/auth/issue-key", json={})
        assert response.status_code == 401

    def test_issue_key_with_master_key(self):
        response = client.post(
            "/api/auth/issue-key",
            json={"role": "user", "ttl_hours": 1},
            headers={"X-API-Key": "test-master-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "api_key" in data
        assert data["role"] == "user"
        assert data["expires_at"] is not None

    def test_verify_master_key(self):
        response = client.get(
            "/api/auth/verify-key",
            headers={"X-API-Key": "test-master-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["type"] == "master"

    def test_verify_invalid_key(self):
        response = client.get(
            "/api/auth/verify-key",
            headers={"X-API-Key": "invalid-key"},
        )
        assert response.status_code == 200
        assert response.json()["valid"] is False


class TestProtectedEndpoints:
    def test_fetch_requires_api_key(self):
        response = client.get("/api/fetch?url=https://www.instagram.com/p/ABC123/")
        assert response.status_code == 401

    def test_fetch_with_invalid_url(self):
        response = client.get(
            "/api/fetch?url=https://www.example.com/",
            headers={"X-API-Key": "test-master-key"},
        )
        assert response.status_code == 400

    def test_proxy_requires_api_key(self):
        response = client.get("/api/proxy?url=https://example.com/file.jpg")
        assert response.status_code == 401

    def test_proxy_with_master_key_invalid_url(self):
        response = client.get(
            "/api/proxy?url=ftp://example.com/file.jpg",
            headers={"X-API-Key": "test-master-key"},
        )
        assert response.status_code == 400
