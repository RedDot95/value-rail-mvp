"""SSRF guard, redirects, politeness, robots.txt and distinct error mapping (offline)."""

from __future__ import annotations

import pytest

from value_rail.connectors.base import SourceUnavailable
from value_rail.net.errors import (AccessDenied, AuthLost, BlockedUrl, NetworkError, RateLimited, RobotsDisallowed,
                                   UpstreamError)
from value_rail.net.http_safe import ip_is_public

from .recorded import PUBLIC_IP, make_client

ROBOTS_OK = (200, {"content-type": "text/plain"}, b"User-agent: *\nDisallow: /checkout\n")
PAGE = (200, {"content-type": "text/html"}, b"<html>ok</html>")
H = "https://www.recharge.com"


@pytest.mark.parametrize("ip,ok", [("10.0.0.1", False), ("127.0.0.1", False), ("169.254.169.254", False),
                                   ("192.168.1.1", False), ("100.64.0.1", False), ("0.0.0.0", False),
                                   ("::1", False), ("fe80::1", False), ("::ffff:10.0.0.1", False),
                                   ("224.0.0.1", False), ("192.0.2.1", False), (PUBLIC_IP, True),
                                   ("2600:9000::1", True)])
def test_ip_classification(ip, ok):
    assert ip_is_public(ip) is ok


@pytest.mark.parametrize("url", ["ftp://www.recharge.com/x", "file:///etc/passwd", "http://www.recharge.com/x",
                                 "https://evil.example/x", "https://13.32.0.10/x", "https://user:pw@www.recharge.com/x",
                                 "gopher://www.recharge.com/", "https://www.recharge.com.evil.example/"])
def test_url_rejected_before_any_request(url):
    client, transport, _ = make_client({})
    with pytest.raises(BlockedUrl):
        client.get(url)
    assert transport.calls == []


def test_private_dns_resolution_blocked():
    client, transport, _ = make_client({}, resolver=lambda h, p: ["10.1.2.3"])
    with pytest.raises(BlockedUrl, match="non-public"):
        client.get(f"{H}/en/de/bitsa")
    assert transport.calls == []


def test_mixed_dns_answer_blocked():
    client, transport, _ = make_client({}, resolver=lambda h, p: [PUBLIC_IP, "127.0.0.1"])
    with pytest.raises(BlockedUrl):
        client.get(f"{H}/en/de/bitsa")


def test_connection_pinned_to_vetted_ip():
    client, transport, _ = make_client({f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": PAGE})
    client.get(f"{H}/a")
    assert {c["ip"] for c in transport.calls} == {PUBLIC_IP}
    assert all("cookie" not in {k.lower() for k in c["headers"]} for c in transport.calls)


def test_redirect_to_foreign_host_blocked():
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": (302, {"location": "https://169.254.169.254/latest"}, b"")}
    client, transport, _ = make_client(routes)
    with pytest.raises(BlockedUrl):
        client.get(f"{H}/a")
    assert all("169.254" not in c["url"] for c in transport.calls)


def test_redirect_to_allowed_host_resolving_private_blocked():
    calls = {"n": 0}

    def resolver(h, p):  # DNS rebinding: first answer public, later private
        calls["n"] += 1
        return [PUBLIC_IP] if calls["n"] <= 2 else ["10.0.0.5"]

    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": (301, {"location": "/b"}, b""), f"{H}/b": PAGE}
    client, _, _ = make_client(routes, resolver=resolver)
    with pytest.raises(BlockedUrl):
        client.get(f"{H}/a")


def test_redirect_same_host_followed_and_recorded():
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": (301, {"location": "/b"}, b""), f"{H}/b": PAGE}
    client, _, _ = make_client(routes)
    res = client.get(f"{H}/a")
    assert res.url == f"{H}/b" and res.redirects == [f"{H}/b"]


def test_redirect_loop_capped():
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": (302, {"location": "/b"}, b""),
              f"{H}/b": (302, {"location": "/a"}, b"")}
    client, _, _ = make_client(routes)
    with pytest.raises(BlockedUrl, match="too many redirects"):
        client.get(f"{H}/a")


def test_redirect_to_login_is_auth_lost():
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": (302, {"location": "/en/de/login?next=/a"}, b"")}
    client, _, _ = make_client(routes)
    with pytest.raises(AuthLost):
        client.get(f"{H}/a")


@pytest.mark.parametrize("status,exc", [(429, RateLimited), (403, AccessDenied), (401, AuthLost), (418, UpstreamError)])
def test_status_mapping_distinct_errors(status, exc):
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": (status, {"retry-after": "120"}, b"")}
    client, transport, clock = make_client(routes)
    with pytest.raises(exc) as ei:
        client.get(f"{H}/a")
    assert isinstance(ei.value, SourceUnavailable)  # a disturbance, never "zero offers"
    assert ei.value.http_status == status
    assert sum(1 for c in transport.calls if c["url"].endswith("/a")) == 1  # no hammering on 4xx
    if status == 429:
        assert ei.value.retry_after_s == 120


def test_5xx_retried_with_backoff_then_success():
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": [(503, {}, b""), (200, {"content-type": "text/html"}, b"ok")]}
    client, transport, clock = make_client(routes, min_interval=0)
    res = client.get(f"{H}/a")
    assert res.status == 200 and res.attempts == 2
    assert any(s >= 2.0 for s in clock.sleeps)  # exponential backoff base


def test_5xx_persistent_is_upstream_error():
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": [(502, {}, b"")]}
    client, transport, _ = make_client(routes, min_interval=0, retries=2)
    with pytest.raises(UpstreamError):
        client.get(f"{H}/a")
    assert sum(1 for c in transport.calls if c["url"].endswith("/a")) == 3


def test_network_errors_retried_then_network_error():
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": [TimeoutError("read timeout")]}
    client, _, clock = make_client(routes, min_interval=0, retries=1)
    with pytest.raises(NetworkError):
        client.get(f"{H}/a")


def test_robots_disallow_prevents_request():
    client, transport, _ = make_client({f"{H}/robots.txt": ROBOTS_OK, f"{H}/checkout": PAGE})
    with pytest.raises(RobotsDisallowed):
        client.get(f"{H}/checkout")
    assert [c["url"] for c in transport.calls] == [f"{H}/robots.txt"]


def test_recorded_recharge_robots_allows_product_pages_only():
    client, transport, _ = make_client(None)
    client._robots_for("https", "www.recharge.com")
    rp = client._robots["www.recharge.com"]
    ua = client.user_agent
    assert rp.can_fetch(ua, f"{H}/en/de/bitsa") and rp.can_fetch(ua, f"{H}/en/de/paysafecard")
    assert not rp.can_fetch(ua, f"{H}/checkout") and not rp.can_fetch(ua, f"{H}/api/v1/whatever")
    assert rp.crawl_delay(ua) == 1


def test_robots_unreadable_refuses():
    client, transport, _ = make_client({f"{H}/robots.txt": (403, {}, b"")})
    with pytest.raises(RobotsDisallowed):
        client.get(f"{H}/a")


def test_robots_404_means_allowed():
    client, _, _ = make_client({f"{H}/a": PAGE})
    assert client.get(f"{H}/a").status == 200


def test_rate_limit_min_interval_and_crawl_delay():
    routes = {f"{H}/robots.txt": (200, {}, b"User-agent: *\nCrawl-delay: 9\n"), f"{H}/a": PAGE, f"{H}/b": PAGE}
    client, _, clock = make_client(routes, min_interval=5.0, jitter=0.0)
    client.get(f"{H}/a")
    client.get(f"{H}/b")
    # robots -> /a -> /b: each later request waits max(min_interval, crawl-delay) = 9 s
    assert clock.sleeps and all(abs(s - 9.0) < 1e-6 for s in clock.sleeps)
    assert len(clock.sleeps) == 2


def test_jitter_added():
    routes = {f"{H}/robots.txt": ROBOTS_OK, f"{H}/a": PAGE}
    client, _, clock = make_client(routes, min_interval=5.0, jitter=2.0)
    client.get(f"{H}/a")
    assert 5.0 <= clock.sleeps[0] <= 7.0
