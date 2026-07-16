"""Integration tests for the FastAPI application."""

from fastapi.testclient import TestClient

from api.index import app


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


def test_fetch_missing_url_parameter():
    response = client.get("/api/fetch")
    assert response.status_code == 422


def test_fetch_invalid_url():
    response = client.get("/api/fetch?url=https://www.example.com/")
    assert response.status_code == 400
    assert "detail" in response.json()


def test_proxy_invalid_scheme():
    response = client.get("/api/proxy?url=ftp://example.com/file.jpg")
    assert response.status_code == 400
