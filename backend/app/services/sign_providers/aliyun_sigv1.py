"""Aliyun Signature V1 provider (HMAC-SHA1)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import urllib.parse

from app.services.sign_providers.base import SignProvider


class AliyunSigV1Provider(SignProvider):
    """Sign Aliyun API requests using Signature V1 (HMAC-SHA1).

    The body field is interpreted as a JSON string of additional query params.
    Common Aliyun signature parameters (Format/Version/AccessKeyId/SignatureMethod/
    SignatureVersion/SignatureNonce/Timestamp) are merged automatically.
    """

    def required_secret_keys(self) -> list[str]:
        return ["access_key_id", "access_key_secret"]

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
        access_key_id = secrets["access_key_id"]
        access_key_secret = secrets["access_key_secret"]

        params: dict[str, str] = {
            "Format": "JSON",
            "Version": "2015-05-01",
            "AccessKeyId": access_key_id,
            "SignatureMethod": "HMAC-SHA1",
            "SignatureVersion": "1.0",
            "SignatureNonce": timestamp,
            "Timestamp": timestamp,
        }
        if query:
            for pair in query.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    params[urllib.parse.unquote(k)] = urllib.parse.unquote(v)

        sorted_params = sorted(params.items())
        canonical_query = "&".join(
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(str(v), safe='')}"
            for k, v in sorted_params
        )

        string_to_sign = (
            f"{method.upper()}&"
            f"{urllib.parse.quote('/', safe='')}&"
            f"{urllib.parse.quote(canonical_query, safe='')}"
        )

        mac = hmac.new(
            f"{access_key_secret}&".encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha1,
        )
        signature = base64.b64encode(mac.digest()).decode("utf-8")
        params["Signature"] = signature
        return params
