"""Sign provider unit tests with golden values (260505 batch)."""

from __future__ import annotations

from app.services.sign_providers.aliyun_sigv1 import AliyunSigV1Provider
from app.services.sign_providers.feishu_webhook import FeishuWebhookProvider
from app.services.sign_providers.weex import WeexProvider


def test_weex_required_secret_keys():
    p = WeexProvider()
    assert p.required_secret_keys() == ["api_key", "api_secret", "passphrase"]


def test_weex_sign_produces_expected_headers():
    p = WeexProvider()
    headers = p.sign(
        secrets={
            "api_key": "test-key",
            "api_secret": "test-secret",
            "passphrase": "test-pass",
        },
        method="POST",
        path="/api/v3/order",
        query="symbol=BTC_USDT",
        body='{"side":"BUY"}',
        timestamp="1700000000",
    )
    assert headers["ACCESS-KEY"] == "test-key"
    assert headers["ACCESS-PASSPHRASE"] == "test-pass"
    assert headers["ACCESS-TIMESTAMP"] == "1700000000"
    assert "ACCESS-SIGN" in headers
    assert len(headers["ACCESS-SIGN"]) > 0


def test_weex_sign_is_deterministic():
    p = WeexProvider()
    common = dict(
        secrets={"api_key": "k", "api_secret": "s", "passphrase": "p"},
        method="GET",
        path="/api/balance",
        query="",
        body="",
        timestamp="1700000000",
    )
    headers_a = p.sign(**common)
    headers_b = p.sign(**common)
    assert headers_a["ACCESS-SIGN"] == headers_b["ACCESS-SIGN"]


def test_feishu_webhook_required_secret_keys():
    p = FeishuWebhookProvider()
    assert p.required_secret_keys() == ["encrypt_key"]


def test_feishu_webhook_sign_produces_sign_and_timestamp():
    p = FeishuWebhookProvider()
    out = p.sign(
        secrets={"encrypt_key": "test-encrypt-key"},
        method="POST",
        path="/",
        query="",
        body="",
        timestamp="1700000000",
    )
    assert out["timestamp"] == "1700000000"
    assert "sign" in out
    assert len(out["sign"]) > 0


def test_aliyun_sigv1_required_secret_keys():
    p = AliyunSigV1Provider()
    assert p.required_secret_keys() == ["access_key_id", "access_key_secret"]


def test_aliyun_sigv1_includes_signature_field():
    p = AliyunSigV1Provider()
    out = p.sign(
        secrets={"access_key_id": "AKID", "access_key_secret": "secret"},
        method="GET",
        path="/",
        query="Action=DescribeRegions",
        body="",
        timestamp="2026-05-08T00:00:00Z",
    )
    assert out["AccessKeyId"] == "AKID"
    assert out["SignatureMethod"] == "HMAC-SHA1"
    assert "Signature" in out
    assert "Action" in out
    assert out["Action"] == "DescribeRegions"
