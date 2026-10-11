"""RFC 9309 robots.txt matcher (replaces urllib.robotparser, which ignores `*`/`$` and later `*` groups)."""

from __future__ import annotations


from value_rail.net.http_safe import DEFAULT_USER_AGENT
from value_rail.net.robots import RobotsRules

UA = DEFAULT_USER_AGENT


def rules(txt: str) -> RobotsRules:
    return RobotsRules(txt.splitlines())


def test_wildcards_and_end_anchor():
    r = rules("User-agent: *\nDisallow: /*?country=*\nDisallow: /*.pdf$\nDisallow: */feed*\n")
    assert not r.can_fetch(UA, "https://x.test/gift-cards/clearance?country=DE")
    assert r.can_fetch(UA, "https://x.test/gift-cards/clearance?page=2")
    assert not r.can_fetch(UA, "https://x.test/a/b.pdf")
    assert r.can_fetch(UA, "https://x.test/a/b.pdf?x=1")  # $ anchors at the end
    assert not r.can_fetch(UA, "https://x.test/blog/feed/")


def test_multiple_star_groups_are_merged():
    # stdlib keeps only the first `*` group; CoinGate's robots.txt has two (the second = Yoast block)
    r = rules("User-agent: *\nDisallow: /checkout/\n\nSitemap: https://x.test/s.xml\n\n"
              "User-agent: *\nDisallow: /*?country=*\n")
    assert not r.can_fetch(UA, "https://x.test/checkout/1")
    assert not r.can_fetch(UA, "https://x.test/gift-cards?country=DE")
    assert r.can_fetch(UA, "https://x.test/gift-cards/bitsa")


def test_longest_match_wins_and_allow_wins_ties():
    r = rules("User-agent: *\nAllow: /*?page=\nDisallow: /*?\nDisallow: /p/\nAllow: /p/\n")
    assert r.can_fetch(UA, "https://x.test/list/?page=2")      # Allow '/*?page=' (8) > Disallow '/*?' (3)
    assert not r.can_fetch(UA, "https://x.test/list/?sort=asc")
    assert r.can_fetch(UA, "https://x.test/p/1")                # equal length -> allow


def test_specific_group_beats_star_and_crawl_delay():
    r = rules("User-agent: *\nDisallow: /\nCrawl-delay: 2\n\nUser-agent: ValueRailMVP\nDisallow: /private\n"
              "Crawl-delay: 9\n")
    assert r.can_fetch(UA, "https://x.test/public")
    assert not r.can_fetch(UA, "https://x.test/private/a")
    assert r.crawl_delay(UA) == 9
    assert not r.can_fetch("OtherBot/1.0", "https://x.test/public")
    assert r.crawl_delay("OtherBot/1.0") == 2


def test_percent_encoding_normalised_and_robots_txt_always_allowed():
    r = rules("User-agent: *\nDisallow: /a[b]\nDisallow: /\n")
    assert not r.can_fetch(UA, "https://x.test/a%5Bb%5D")
    assert r.can_fetch(UA, "https://x.test/robots.txt")


def test_empty_disallow_and_no_rules_allow_everything():
    assert rules("User-agent: *\nDisallow: \n").can_fetch(UA, "https://x.test/anything")
    assert RobotsRules([]).can_fetch(UA, "https://x.test/anything")
