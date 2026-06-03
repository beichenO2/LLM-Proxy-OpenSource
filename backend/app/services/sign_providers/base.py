"""Base class for sign providers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SignProvider(ABC):
    """Abstract HMAC signing provider.

    Each provider takes secret credentials (decrypted internally, never returned)
    and a request description, then produces the auth headers needed to call
    the upstream service.
    """

    @abstractmethod
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
        """Return a dict of HTTP headers to authenticate the request."""
        ...

    @abstractmethod
    def required_secret_keys(self) -> list[str]:
        """List the secret keys this provider needs from the vault."""
        ...
