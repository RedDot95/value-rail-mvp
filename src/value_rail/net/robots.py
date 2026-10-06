"""RFC 9309 robots.txt matcher.

Why not `urllib.robotparser`: the stdlib parser (a) does not understand the `*` and `$` path wildcards
(so `Disallow: /*?country=*` never matches anything) and (b) only keeps the FIRST `User-agent: *` group,
silently dropping later ones (CoinGate's robots.txt has two `*` groups). Both make it UNDER-block, which
is the wrong direction for a polite crawler.

Semantics implemented (RFC 9309):
- groups start with one or more consecutive `user-agent` lines; rules before any group are ignored;
- the crawler uses all groups whose user-agent equals its product token (case-insensitive), merged;
  if none, all `*` groups, merged;
- the longest matching path pattern wins; on a tie `allow` wins; no match = allowed;
- `*` matches any sequence, a trailing `$` anchors at the end; matching is against path + query;
- `/robots.txt` itself is always allowed;
- `crawl-delay` (non-standard) is honoured: largest value among the selected groups.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import quote, unquote, urlsplit

_SAFE = "/?&=*$:@!,;+~-._'()[]%"


def _norm(s: str) -> str:
    # canonical percent-encoding so "%5B" and "[" compare equal
    return quote(unquote(s), safe=_SAFE.replace("%", ""))


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)  # (allow, pattern)
    crawl_delay: float | None = None


def _compile(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    rx = ".*".join(re.escape(part) for part in body.split("*"))
    return re.compile(rx + ("$" if anchored else ""))


class RobotsRules:
    def __init__(self, lines: list[str] | None = None) -> None:
        self.groups: list[_Group] = []
        self.sitemaps: list[str] = []
        self._cache: dict[str, tuple[list[tuple[bool, str, re.Pattern[str]]], float | None]] = {}
        if lines:
            self.parse(lines)

    def parse(self, lines: list[str]) -> None:
        cur: _Group | None = None
        last_was_agent = False
        for raw in lines:
            line = raw.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            key, val = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key in ("user-agent", "useragent"):
                if cur is None or not last_was_agent:
                    cur = _Group()
                    self.groups.append(cur)
                cur.agents.append(val.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if key == "sitemap":
                self.sitemaps.append(val)
            elif cur is None:
                continue
            elif key in ("allow", "disallow"):
                if val:  # empty Disallow = allow all; empty Allow = no-op
                    cur.rules.append((key == "allow", _norm(val)))
            elif key == "crawl-delay":
                try:
                    d = float(val)
                    cur.crawl_delay = d if cur.crawl_delay is None else max(cur.crawl_delay, d)
                except ValueError:
                    pass
        self._cache.clear()

    @staticmethod
    def product_token(user_agent: str) -> str:
        m = re.match(r"[A-Za-z_-]+", user_agent.strip())
        return (m.group(0) if m else user_agent).lower()

    def _select(self, user_agent: str) -> tuple[list[tuple[bool, str, re.Pattern[str]]], float | None]:
        token = self.product_token(user_agent)
        if token in self._cache:
            return self._cache[token]
        groups = [g for g in self.groups if token in g.agents]
        if not groups:
            groups = [g for g in self.groups if "*" in g.agents]
        rules = [(a, p, _compile(p)) for g in groups for (a, p) in g.rules]
        delays = [g.crawl_delay for g in groups if g.crawl_delay is not None]
        self._cache[token] = (rules, max(delays) if delays else None)
        return self._cache[token]

    def can_fetch(self, user_agent: str, url: str) -> bool:
        parts = urlsplit(url)
        path = parts.path or "/"
        if path == "/robots.txt":
            return True
        target = _norm(path + (f"?{parts.query}" if parts.query else ""))
        best: tuple[int, bool] | None = None  # (pattern length, allow)
        for allow, pat, rx in self._select(user_agent)[0]:
            if rx.match(target):
                cand = (len(pat), allow)
                if best is None or cand[0] > best[0] or (cand[0] == best[0] and allow):
                    best = cand
        return True if best is None else best[1]

    def crawl_delay(self, user_agent: str) -> float | None:
        return self._select(user_agent)[1]
