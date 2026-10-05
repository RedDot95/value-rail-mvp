"""SSRF-safe, polite HTTP client (stdlib only).

Guarantees
- Only http/https URLs whose host is on an explicit per-client allowlist.
- Host is resolved ONCE per request; every resolved address must be globally routable
  (no private, loopback, link-local, multicast, reserved, unspecified, CGNAT, IPv4-mapped-private).
  The TCP connection is then made to exactly that vetted IP (TLS SNI + certificate check still use
  the hostname), which closes the DNS-rebinding window between check and connect.
- Redirects are NEVER followed automatically; each hop is re-validated with the same rules (max 3).
- Timeouts on connect/read, maximum body size.
- Per-host minimum interval (max(configured, robots Crawl-delay)) plus random jitter.
- Retries with exponential backoff only for network errors and 5xx. 429/403/401 are reported
  immediately as distinct errors (we never hammer and never try to bypass a block).
- Optional robots.txt check (fetched through this same guarded client and cached).
- Response headers are not persisted by callers (Set-Cookie etc. could carry client data); we
  expose only status, final URL, content-type and body.

The transport and resolver are injectable so the whole client is testable offline.
"""

from __future__ import annotations

import gzip
import http.client
import ipaddress
import random
import socket
import ssl
import time
import urllib.robotparser
import zlib
from dataclasses import dataclass, field
from typing import Callable, Protocol
from urllib.parse import urljoin, urlsplit

from .errors import (AccessDenied, AuthLost, BlockedUrl, NetworkError, RateLimited, RobotsDisallowed,
                     UpstreamError)

DEFAULT_USER_AGENT = "ValueRailMVP/0.3 (private price research; polite; honors robots.txt)"
MAX_REDIRECTS = 3


@dataclass
class TransportResponse:
    status: int
    headers: dict[str, str]  # lower-cased header names
    body: bytes


class Transport(Protocol):
    def __call__(self, *, method: str, url: str, ip: str, headers: dict[str, str], body: bytes | None,
                 timeout: float, max_bytes: int) -> TransportResponse: ...


Resolver = Callable[[str, int], list[str]]


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({i[4][0] for i in infos})


def ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast or addr.is_reserved
            or addr.is_unspecified or getattr(addr, "is_site_local", False)):
        return False
    if isinstance(addr, ipaddress.IPv4Address) and addr in ipaddress.ip_network("100.64.0.0/10"):
        return False  # carrier-grade NAT
    return addr.is_global


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float, context: ssl.SSLContext) -> None:
        super().__init__(host, port, timeout=timeout, context=context)
        self._pinned_ip = ip

    def connect(self) -> None:  # connect to the vetted IP, verify TLS against the hostname
        sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


class _PinnedHTTPConnection(http.client.HTTPConnection):
    def __init__(self, host: str, ip: str, port: int, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._pinned_ip = ip

    def connect(self) -> None:
        self.sock = socket.create_connection((self._pinned_ip, self.port), self.timeout)


def stdlib_transport(*, method: str, url: str, ip: str, headers: dict[str, str], body: bytes | None,
                     timeout: float, max_bytes: int) -> TransportResponse:
    parts = urlsplit(url)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if parts.scheme == "https":
        conn: http.client.HTTPConnection = _PinnedHTTPSConnection(parts.hostname, ip, port, timeout,
                                                                  ssl.create_default_context())
    else:
        conn = _PinnedHTTPConnection(parts.hostname, ip, port, timeout)
    path = parts.path or "/"
    if parts.query:
        path += "?" + parts.query
    try:
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError(f"response larger than {max_bytes} bytes")
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        enc = hdrs.get("content-encoding", "").lower()
        if enc == "gzip":
            raw = gzip.decompress(raw)
        elif enc == "deflate":
            raw = zlib.decompress(raw)
        return TransportResponse(status=resp.status, headers=hdrs, body=raw)
    finally:
        conn.close()


@dataclass
class FetchResult:
    url: str  # final URL after validated redirects
    status: int
    content_type: str
    body: bytes
    fetched_monotonic: float
    redirects: list[str] = field(default_factory=list)
    attempts: int = 1

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


@dataclass
class PolitenessPolicy:
    min_interval_s: float = 5.0
    jitter_s: float = 2.0
    max_retries: int = 2
    backoff_base_s: float = 2.0
    backoff_max_s: float = 60.0


class SafeHttpClient:
    def __init__(self, *, source_key: str, allowed_hosts: set[str], allow_http: bool = False,
                 user_agent: str = DEFAULT_USER_AGENT, connect_timeout_s: float = 10.0,
                 max_bytes: int = 3_000_000, policy: PolitenessPolicy | None = None, respect_robots: bool = True,
                 transport: Transport | None = None, resolver: Resolver | None = None,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic,
                 rng: random.Random | None = None, robots_ttl_s: float = 86400.0) -> None:
        if not allowed_hosts:
            raise ValueError("allowed_hosts must not be empty")
        self.source_key = source_key
        self.allowed_hosts = {h.lower().rstrip(".") for h in allowed_hosts}
        self.allow_http = allow_http
        self.user_agent = user_agent
        self.timeout = connect_timeout_s
        self.max_bytes = max_bytes
        self.policy = policy or PolitenessPolicy()
        self.respect_robots = respect_robots
        self.transport = transport or stdlib_transport
        self.resolver = resolver or system_resolver
        self.sleep = sleep
        self.monotonic = monotonic
        self.rng = rng or random.Random()
        self._last_request: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._robots_at: dict[str, float] = {}
        self.robots_ttl_s = robots_ttl_s  # long-running worker re-reads robots.txt daily
        self.request_log: list[tuple[str, int | str]] = []  # (url, status|error) for diagnostics/tests

    # ---------- validation ----------
    def validate_url(self, url: str) -> tuple[str, int, str]:
        """Return (host, port, vetted_ip) or raise BlockedUrl."""
        try:
            parts = urlsplit(url)
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError as exc:
            raise BlockedUrl(self.source_key, f"unparsable URL: {exc}", url=url) from None
        allowed_schemes = {"https", "http"} if self.allow_http else {"https"}
        if parts.scheme not in allowed_schemes:
            raise BlockedUrl(self.source_key, f"scheme {parts.scheme!r} not allowed", url=url)
        if parts.username or parts.password:
            raise BlockedUrl(self.source_key, "credentials in URL not allowed", url=url)
        host = (parts.hostname or "").lower().rstrip(".")
        if not host or host not in self.allowed_hosts:
            raise BlockedUrl(self.source_key, f"host {host!r} not on allowlist", url=url)
        try:
            ipaddress.ip_address(host)
            raise BlockedUrl(self.source_key, "literal IP hosts are not allowed", url=url)
        except ValueError:
            pass
        try:
            ips = self.resolver(host, port)
        except OSError as exc:
            raise NetworkError(self.source_key, f"DNS resolution failed for {host}: {exc}", url=url) from None
        if not ips:
            raise NetworkError(self.source_key, f"DNS returned no address for {host}", url=url)
        bad = [ip for ip in ips if not ip_is_public(ip)]
        if bad:
            raise BlockedUrl(self.source_key, f"{host} resolves to non-public address(es) {bad}", url=url)
        return host, port, ips[0]

    # ---------- politeness ----------
    def _wait_turn(self, host: str) -> None:
        interval = self.policy.min_interval_s
        rp = self._robots.get(host)
        if rp is not None:
            cd = rp.crawl_delay(self.user_agent)
            if cd:
                interval = max(interval, float(cd))
        last = self._last_request.get(host)
        if last is not None:
            wait = interval - (self.monotonic() - last) + self.rng.uniform(0, self.policy.jitter_s)
            if wait > 0:
                self.sleep(wait)
        self._last_request[host] = self.monotonic()

    def _robots_for(self, scheme: str, host: str) -> urllib.robotparser.RobotFileParser | None:
        if host in self._robots and self.monotonic() - self._robots_at.get(host, 0.0) < self.robots_ttl_s:
            return self._robots[host]
        url = f"{scheme}://{host}/robots.txt"
        rp = urllib.robotparser.RobotFileParser(url)
        try:
            res = self._request("GET", url, check_robots=False)
        except (RateLimited, AccessDenied, AuthLost) as exc:
            raise RobotsDisallowed(self.source_key, f"robots.txt not readable ({exc.code}); refusing to crawl",
                                   url=url) from None
        if res.status == 404:
            rp.parse([])  # no robots.txt = no restrictions (RFC 9309 2.3.1.3)
        elif 200 <= res.status < 300:
            rp.parse(res.text().splitlines())
        else:
            raise RobotsDisallowed(self.source_key, f"robots.txt returned HTTP {res.status}; refusing to crawl",
                                   url=url)
        self._robots[host] = rp
        self._robots_at[host] = self.monotonic()
        return rp

    # ---------- request ----------
    def get(self, url: str, *, accept: str = "text/html,application/xhtml+xml") -> FetchResult:
        return self._request("GET", url, headers={"Accept": accept})

    def post_json(self, url: str, body: bytes) -> FetchResult:
        return self._request("POST", url, headers={"Content-Type": "application/json",
                                                   "Accept": "application/json"}, body=body)

    def _request(self, method: str, url: str, *, headers: dict[str, str] | None = None, body: bytes | None = None,
                 check_robots: bool | None = None) -> FetchResult:
        check_robots = self.respect_robots if check_robots is None else check_robots
        redirects: list[str] = []
        current = url
        for _hop in range(MAX_REDIRECTS + 1):
            host, _port, ip = self.validate_url(current)
            scheme = urlsplit(current).scheme
            if check_robots:
                rp = self._robots_for(scheme, host)
                if rp is not None and not rp.can_fetch(self.user_agent, current):
                    raise RobotsDisallowed(self.source_key, f"robots.txt disallows {current}", url=current)
            resp, attempts = self._send_with_retries(method, current, ip, host, headers or {}, body)
            if resp.status in (301, 302, 303, 307, 308):
                loc = resp.headers.get("location")
                if not loc:
                    raise UpstreamError(self.source_key, f"redirect without Location from {current}", url=current,
                                        http_status=resp.status)
                nxt = urljoin(current, loc)
                redirects.append(nxt)
                low = nxt.lower()
                if any(k in low for k in ("/login", "/signin", "/sign-in", "/account")):
                    raise AuthLost(self.source_key, f"redirected to login/account page {nxt}", url=current,
                                   http_status=resp.status)
                if resp.status == 303:
                    method, body = "GET", None
                current = nxt
                continue  # next loop iteration re-validates scheme/host/IP of the redirect target
            return self._classify(method, current, resp, redirects, attempts)
        raise BlockedUrl(self.source_key, f"too many redirects (> {MAX_REDIRECTS})", url=url)

    def _send_with_retries(self, method: str, url: str, ip: str, host: str, headers: dict[str, str],
                           body: bytes | None) -> tuple[TransportResponse, int]:
        hdrs = {"User-Agent": self.user_agent, "Accept-Encoding": "gzip", "Accept-Language": "en,de;q=0.8",
                "Connection": "close"} | headers
        attempt = 0
        while True:
            attempt += 1
            self._wait_turn(host)
            try:
                resp = self.transport(method=method, url=url, ip=ip, headers=hdrs, body=body, timeout=self.timeout,
                                      max_bytes=self.max_bytes)
            except (OSError, http.client.HTTPException, ValueError, ssl.SSLError) as exc:
                self.request_log.append((url, type(exc).__name__))
                if attempt > self.policy.max_retries:
                    raise NetworkError(self.source_key, f"{type(exc).__name__}: {exc}", url=url) from None
                self.sleep(self._backoff(attempt))
                continue
            self.request_log.append((url, resp.status))
            if 500 <= resp.status < 600 and attempt <= self.policy.max_retries:
                self.sleep(self._backoff(attempt, resp.headers.get("retry-after")))
                continue
            return resp, attempt

    def _backoff(self, attempt: int, retry_after: str | None = None) -> float:
        base = min(self.policy.backoff_max_s, self.policy.backoff_base_s * (2 ** (attempt - 1)))
        ra = _parse_retry_after(retry_after)
        if ra is not None:
            base = max(base, min(ra, self.policy.backoff_max_s))
        return base + self.rng.uniform(0, self.policy.jitter_s)

    def _classify(self, method: str, url: str, resp: TransportResponse, redirects: list[str],
                  attempts: int) -> FetchResult:
        st = resp.status
        if st == 429:
            raise RateLimited(self.source_key, f"HTTP 429 from {url}", url=url, http_status=st,
                              retry_after_s=_parse_retry_after(resp.headers.get("retry-after")))
        if st == 403:
            raise AccessDenied(self.source_key, f"HTTP 403 from {url} (bot protection/geo block?) - not bypassed",
                               url=url, http_status=st)
        if st == 401:
            raise AuthLost(self.source_key, f"HTTP 401 from {url}", url=url, http_status=st)
        if st >= 500 or (st >= 400 and st != 404):
            raise UpstreamError(self.source_key, f"HTTP {st} from {url}", url=url, http_status=st)
        return FetchResult(url=url, status=st, content_type=resp.headers.get("content-type", ""), body=resp.body,
                           fetched_monotonic=self.monotonic(), redirects=redirects, attempts=attempts)


def _parse_retry_after(v: str | None) -> float | None:
    if not v:
        return None
    try:
        return max(0.0, float(v))
    except ValueError:
        return None
