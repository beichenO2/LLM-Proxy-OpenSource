"""Tests for GET/PUT /api/settings (STNG-01, STNG-03)."""

from __future__ import annotations


def test_settings_put_get_roundtrip(client):
    r = client.put(
        "/api/settings",
        json={"api_port": 9090, "preferences": {"theme": "dark", "locale": "en"}},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["api_port"] == 9090
    assert data["preferences"] == {"theme": "dark", "locale": "en"}

    r2 = client.get("/api/settings")
    assert r2.status_code == 200
    assert r2.json() == data


def test_settings_get_defaults_when_missing_row(client):
    r = client.get("/api/settings")
    assert r.status_code == 200
    j = r.json()
    assert "api_port" in j
    assert "preferences" in j
    assert isinstance(j["preferences"], dict)
