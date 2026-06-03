"""Feishu webhook HMAC-SHA256 signing provider.

Spec: timestamp + "\\n" + secret → HMAC-SHA256(empty data, key=string_to_sign) → base64
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from app.services.sign_providers.base import SignProvider


class FeishuWebhookProvider(SignProvider):
    """Sign Feishu webhook requests using HMAC-SHA256 + Base64."""

    def required_secret_keys(self) -> list[str]:
        return ["encrypt_key"]

    def sign(
        self,
        *,
        secrets: dict[str, str],
        method: str,
        path: str,
        query: str,
        body: str,
        timestamp: str,
    ) -> dict[str, str]:
        encrypt_key = secrets["encrypt_key"]
        string_to_sign = f"{timestamp}\n{encrypt_key}"
        hmac_code = hmac.new(
            string_to_sign.encode("utf-8"),
            b"",
            hashlib.sha256,
        ).digest()
        sign_value = base64.b64encode(hmac_code).decode("utf-8")

        return {
            "sign": sign_value,
            "timestamp": timestamp,
        }
