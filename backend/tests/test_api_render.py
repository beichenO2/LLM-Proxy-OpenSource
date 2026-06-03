"""Tests for POST /api/render (D-42, TMPL-05, TMPL-06)."""

from __future__ import annotations


def test_render_minimal_template(client):
    r = client.post("/api/render", json={"template": "x"})
    assert r.status_code == 200
    data = r.json()
    assert set(data.keys()) >= {"rendered", "warnings", "stats"}
    assert data["rendered"] == "x"
    assert isinstance(data["warnings"], list)
    assert isinstance(data["stats"], dict)


def test_render_secret_ref_placeholder(client):
    """secret_ref placeholders render as tags."""
    r = client.post("/api/render", json={"template": "Value: [[secret_ref.test.key]]"})
    assert r.status_code == 200
    data = r.json()
    assert "[secret_ref:test.key]" in data["rendered"]


def test_secret_ref_is_tag_only_no_fernet_in_rendered(client):
    r = client.post(
        "/api/render",
        json={"template": "[[secret_ref.secret.x.y]]"},
    )
    assert r.status_code == 200
    data = r.json()
    rendered = data["rendered"]
    assert "[secret_ref:secret.x.y]" in rendered
    assert "gAAAA" not in rendered
