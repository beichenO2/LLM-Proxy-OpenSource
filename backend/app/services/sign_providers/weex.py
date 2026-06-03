"""WEEX exchange HMAC-SHA256 signing provider.

Signature formula from WEEX REST API spec:
    prehash = timestamp + method + (path + "?" + query)? + body
    signature = base64(hmac_sha256(api_secret, prehash))
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from app.services.sign_providers.base import SignProvider


class WeexProvider(SignProvider):
    """Sign WEEX REST API requests using HMAC-SHA256."""

    def required_secret_keys(self) -> list[str]:
        return ["api_key", "api_secret", "passphrase"]

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
        api_key = secrets["api_key"]
        api_secret = secrets["api_secret"]
        passphrase = secrets["passphrase"]

        request_path = f"{path}?{query}" if query else path
        prehash = f"{timestamp}{method.upper()}{request_path}{body}"

        mac = hmac.new(
            api_secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        )
        signature = base64.b64encode(mac.digest()).decode("utf-8")

        return {
            "ACCESS-KEY": api_key,
            "ACCESS-SIGN": signature,
            "ACCESS-TIMESTAMP": timestamp,
            "ACCESS-PASSPHRASE": passphrase,
        }
