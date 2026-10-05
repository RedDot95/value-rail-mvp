"""Offline replay of recorded real responses (tests/fixtures/recorded/...). No network access."""

from __future__ import annotations

import json
import random
from pathlib import Path

from value_rail.net.http_safe import PolitenessPolicy, SafeHttpClient, TransportResponse

REC = Path(__file__).resolve().parent / "fixtures" / "recorded" / "recharge_com_2026-10-05"
PUBLIC_IP = "13.32.0.10"  # a public address; never contacted (fake transport)


def recorded_routes() -> dict[str, tuple[int, dict[str, str], bytes]]:
    meta = json.loads((REC / "meta.json").read_text())
    routes = {}
    for fname, m in meta["files"].items():
        routes[m["url"]] = (m["http_status"], {"content-type": m["content_type"]}, (REC / fname).read_bytes())
    return routes


class FakeTransport:
    def __init__(self, routes: dict[str, object]) -> None:
        self.routes = dict(routes)
        self.calls: list[dict] = []

    def __call__(self, *, method, url, ip, headers, body, timeout, max_bytes):
        self.calls.append({"method": method, "url": url, "ip": ip, "headers": headers, "body": body})
        r = self.routes.get(url)
        if r is None:
            return TransportResponse(status=404, headers={"content-type": "text/plain"}, body=b"not found")
        if callable(r):
            r = r()
        if isinstance(r, Exception):
            raise r
        if isinstance(r, list):  # sequence of responses
            nxt = r.pop(0) if len(r) > 1 else r[0]
            if isinstance(nxt, Exception):
                raise nxt
            st, h, b = nxt
        else:
            st, h, b = r
        return TransportResponse(status=st, headers=h, body=b)


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def make_client(routes=None, *, resolver=None, allowed=("www.recharge.com",), min_interval=5.0, jitter=0.0,
                retries=2, clock: FakeClock | None = None, respect_robots=True, **kw):
    clock = clock or FakeClock()
    transport = FakeTransport(recorded_routes() if routes is None else routes)
    client = SafeHttpClient(source_key="recharge-com-de", allowed_hosts=set(allowed), transport=transport,
                            resolver=resolver or (lambda h, p: [PUBLIC_IP]),
                            policy=PolitenessPolicy(min_interval_s=min_interval, jitter_s=jitter, max_retries=retries,
                                                    backoff_base_s=2.0),
                            sleep=clock.sleep, monotonic=clock.monotonic, rng=random.Random(7),
                            respect_robots=respect_robots, **kw)
    return client, transport, clock
