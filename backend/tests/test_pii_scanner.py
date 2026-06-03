"""Tests for PII pattern scanner service and API endpoints."""

from __future__ import annotations

import pytest
from app.services.pii_scanner import scan_text, redact_text, get_patterns


class TestScanText:
    def test_detects_email(self):
        result = scan_text("Contact me at alice@example.com for details.")
        assert result.has_pii
        emails = [m for m in result.matches if m.label == "email"]
        assert len(emails) == 1
        assert emails[0].text == "alice@example.com"

    def test_detects_chinese_phone(self):
        result = scan_text("我的手机号是13812345678，请联系我。")
        phones = [m for m in result.matches if m.label == "phone_cn"]
        assert len(phones) == 1
        assert phones[0].text == "13812345678"

    def test_detects_chinese_id_card(self):
        result = scan_text("身份证号 110101199003074215 已登记")
        ids = [m for m in result.matches if m.label == "id_card_cn"]
        assert len(ids) == 1
        assert ids[0].text == "110101199003074215"

    def test_detects_ipv4(self):
        result = scan_text("Server at 192.168.1.100 is down")
        ips = [m for m in result.matches if m.label == "ipv4"]
        assert len(ips) == 1
        assert ips[0].text == "192.168.1.100"

    def test_detects_api_key(self):
        result = scan_text("Use sk-proj-abc123def456ghi789 for auth")
        keys = [m for m in result.matches if m.label == "api_key"]
        assert len(keys) == 1
        assert "sk-proj" in keys[0].text

    def test_detects_jwt(self):
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc123def456"
        result = scan_text(f"Bearer {token}")
        jwts = [m for m in result.matches if m.label == "jwt"]
        assert len(jwts) == 1

    def test_detects_multiple_types(self):
        text = "Email: test@example.com, Phone: 13900001234, IP: 10.0.0.1"
        result = scan_text(text)
        labels = {m.label for m in result.matches}
        assert "email" in labels
        assert "phone_cn" in labels
        assert "ipv4" in labels

    def test_no_pii_in_clean_text(self):
        result = scan_text("This is a perfectly clean sentence with no PII.")
        assert not result.has_pii
        assert len(result.matches) == 0

    def test_match_positions_are_correct(self):
        text = "hello alice@test.com world"
        result = scan_text(text)
        m = result.matches[0]
        assert text[m.start:m.end] == "alice@test.com"

    def test_url_with_token(self):
        result = scan_text("Visit https://api.example.com/v1?token=abc123xyz for access")
        urls = [m for m in result.matches if m.label == "url_with_token"]
        assert len(urls) == 1

    def test_chinese_passport(self):
        result = scan_text("护照号 E12345678 已过期")
        passports = [m for m in result.matches if m.label == "passport_cn"]
        assert len(passports) == 1


class TestRedactText:
    def test_replaces_email(self):
        text = "Send to bob@example.com please"
        redacted, result = redact_text(text)
        assert "bob@example.com" not in redacted
        assert "[[email]]" in redacted
        assert result.has_pii

    def test_replaces_multiple(self):
        text = "Email: a@b.com, Phone: 13800138000"
        redacted, result = redact_text(text)
        assert "a@b.com" not in redacted
        assert "13800138000" not in redacted
        assert "[[email]]" in redacted
        assert "[[phone_cn]]" in redacted

    def test_clean_text_unchanged(self):
        text = "Nothing to see here"
        redacted, result = redact_text(text)
        assert redacted == text
        assert not result.has_pii

    def test_custom_placeholder(self):
        text = "My email is x@y.com"
        redacted, _ = redact_text(text, placeholder="<REDACTED:{label}>")
        assert "<REDACTED:email>" in redacted


class TestGetPatterns:
    def test_returns_list(self):
        patterns = get_patterns()
        assert isinstance(patterns, list)
        assert len(patterns) > 0

    def test_pattern_has_required_keys(self):
        p = get_patterns()[0]
        assert "label" in p
        assert "description" in p
        assert "pattern" in p


class TestScanApi:
    def test_scan_endpoint(self, client):
        r = client.post("/api/sanitize/scan", json={"text": "Contact alice@example.com"})
        assert r.status_code == 200
        data = r.json()
        assert data["has_pii"] is True
        assert data["count"] == 1
        assert data["matches"][0]["label"] == "email"

    def test_scan_no_pii(self, client):
        r = client.post("/api/sanitize/scan", json={"text": "No sensitive data here"})
        assert r.status_code == 200
        assert r.json()["has_pii"] is False
        assert r.json()["count"] == 0

    def test_redact_endpoint(self, client):
        r = client.post(
            "/api/sanitize/redact",
            json={"text": "Call me at 13912345678"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["has_pii"] is True
        assert "13912345678" not in data["redacted"]
        assert "[[phone_cn]]" in data["redacted"]

    def test_patterns_endpoint(self, client):
        r = client.get("/api/sanitize/patterns")
        assert r.status_code == 200
        patterns = r.json()
        assert len(patterns) > 0
        labels = {p["label"] for p in patterns}
        assert "email" in labels
        assert "phone_cn" in labels
