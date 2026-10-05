"""Distinct fetch errors. Every one of them is a DISTURBANCE (SourceUnavailable), never 'zero offers'."""

from __future__ import annotations

from ..connectors.base import SourceUnavailable


class FetchError(SourceUnavailable):
    code = "fetch_error"

    def __init__(self, source_key: str, message: str, *, url: str = "", http_status: int | None = None,
                 retry_after_s: float | None = None) -> None:
        super().__init__(source_key, f"[{self.code}] {message}")
        self.url = url
        self.http_status = http_status
        self.retry_after_s = retry_after_s


class BlockedUrl(FetchError):
    """URL rejected by the SSRF guard (scheme, host allowlist, private/reserved IP, redirect target)."""
    code = "blocked_url"


class RobotsDisallowed(FetchError):
    code = "robots_disallowed"


class RateLimited(FetchError):
    """HTTP 429. We stop and report; we never hammer."""
    code = "rate_limited_429"


class AccessDenied(FetchError):
    """HTTP 403 (bot protection / geo block / WAF). Never bypassed."""
    code = "access_denied_403"


class AuthLost(FetchError):
    """HTTP 401 or redirect to a login page: credentials/session missing or expired."""
    code = "auth_lost"


class UpstreamError(FetchError):
    """5xx after retries, or other unexpected HTTP status."""
    code = "upstream_error"


class NetworkError(FetchError):
    """DNS / connect / TLS / timeout problems after retries."""
    code = "network_error"


class ParserBroken(FetchError):
    """Page fetched but the expected machine-readable structure is missing/changed."""
    code = "parser_broken"


class UnexpectedEmpty(FetchError):
    """Structure present but contains no offers where offers are expected."""
    code = "unexpected_empty"
