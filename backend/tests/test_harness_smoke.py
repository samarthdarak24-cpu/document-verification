"""Smoke test for the isolated test harness itself."""

from __future__ import annotations


def test_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["app"] == "DocuTrace"
    assert body["database"] == "ok"


def test_openapi_schema_is_served(client):
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"]
    # Every router must have contributed at least one path.
    assert len(schema["paths"]) >= 20


def test_database_is_isolated_from_the_dev_database(client):
    from app.core.config import get_settings

    settings = get_settings()
    assert "docutrace-tests-" in settings.DATABASE_URL
    # Fresh schema ⇒ no documents yet.
    r = client.get("/api/documents")
    assert r.status_code == 200
    assert r.json() == [] or r.json().get("items") == []
