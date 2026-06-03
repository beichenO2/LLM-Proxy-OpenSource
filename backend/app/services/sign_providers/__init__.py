"""Sign providers — HMAC/signature services for B-class secrets.

Each provider implements sign() → dict of headers.
Secret material never leaves the PolarPrivate process boundary.
"""

from app.services.sign_providers.weex import WeexProvider
from app.services.sign_providers.feishu_webhook import FeishuWebhookProvider
from app.services.sign_providers.aliyun_sigv1 import AliyunSigV1Provider

PROVIDERS: dict[str, type] = {
    "weex": WeexProvider,
    "feishu-webhook": FeishuWebhookProvider,
    "aliyun-sigv1": AliyunSigV1Provider,
}
