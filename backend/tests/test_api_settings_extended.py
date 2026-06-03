"""Extended settings API tests — edge cases, preferences parsing."""

from __future__ import annotations

from app.api.settings import parse_preferences_json


def test_parse_preferences_json_empty_string():
    assert parse_preferences_json("") == {}


def test_parse_preferences_json_none():
    assert parse_preferences_json(None) == {}


def test_parse_preferences_json_valid():
    assert parse_preferences_json('{"theme": "dark"}') == {"theme": "dark"}


def test_parse_preferences_json_invalid():
    assert parse_preferences_json("not json") == {}


def test_parse_preferences_json_non_dict():
    """JSON that parses but is not a dict returns empty dict."""
    assert parse_preferences_json("[1,2,3]") == {}


def test_settings_put_preferences(client):
    r = client.put("/api/settings", json={"preferences": {"theme": "dark", "lang": "zh"}})
    assert r.status_code == 200
    data = r.json()
    assert data["preferences"]["theme"] == "dark"
    assert data["preferences"]["lang"] == "zh"


def test_settings_put_api_port(client):
    r = client.put("/api/settings", json={"api_port": 9090})
    assert r.status_code == 200
    assert r.json()["api_port"] == 9090

    r = client.get("/api/settings")
    assert r.json()["api_port"] == 9090


def test_settings_put_null_preferences_resets(client):
    """Setting preferences=null resets to empty dict."""
    client.put("/api/settings", json={"preferences": {"key": "val"}})
    r = client.put("/api/settings", json={"preferences": None})
    assert r.status_code == 200
    assert r.json()["preferences"] == {}


def test_settings_put_creates_row_if_missing(client):
    """First PUT creates the settings row."""
    r = client.put("/api/settings", json={"api_port": 8000})
    assert r.status_code == 200
    assert r.json()["api_port"] == 8000
