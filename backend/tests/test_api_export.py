"""Tests for POST /api/export (EXPT-01–EXPT-05)."""

from __future__ import annotations


def test_export_markdown_binding_tag(client):
    """Export with binding placeholder renders as tag."""
    r = client.post(
        "/api/export",
        json={"template": "Service: [[binding.test.service]]", "format": "markdown"},
    )
    assert r.status_code == 200
    assert "text/markdown" in (r.headers.get("content-type") or "")
    assert "[ERROR:" in r.text or "[secret_ref:" in r.text


def test_export_html_binding_tag(client):
    """Export with binding placeholder in HTML format."""
    r = client.post(
        "/api/export",
        json={"template": "Service: [[binding.test.service]]", "format": "html"},
    )
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "")
    body = r.text.lower()
    assert "<html" in body


def test_export_txt_no_bold_markers(client):
    """TXT export does not include markdown bold markers."""
    r = client.post(
        "/api/export",
        json={"template": "Plain text [[secret_ref.test.key]]", "format": "txt"},
    )
    assert r.status_code == 200
    assert "text/plain" in (r.headers.get("content-type") or "")
    assert "**" not in r.text


def test_export_secret_ref_is_tag_not_plaintext(client):
    r = client.post(
        "/api/export",
        json={
            "template": "[[secret_ref.secret.z.z]]",
            "format": "markdown",
        },
    )
    assert r.status_code == 200
    assert "[secret_ref:secret.z.z]" in r.text
