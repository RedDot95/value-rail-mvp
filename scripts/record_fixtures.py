"""Record stripped, dated offline fixtures for a live connector (uses the same SafeHttpClient: robots.txt,
>=5 s/host + jitter, allowlist). Keeps only <title> and schema.org ld+json blocks - no cookies, no headers,
no personal data. Aggregator kinds (coingate_mcp, bsv_list, cardbear_html, gcw_hotdeals) are recorded by
`record_aggregator()` with their own minimal, personal-data-free extracts (see that function).
Usage: python scripts/record_fixtures.py <connector-key> [--config config/production.toml]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from value_rail.connectors.aggregators import (AGGREGATOR_KINDS, BsvPage, CardBearPage, CoinGateBrand, CoinGateSearch,
                                              build_aggregator, bsv_products, pseudonym)
from value_rail.connectors.jsonld_shop import JsonLdShopConfig
from value_rail.connectors.recharge import BASE_URL as RECHARGE_BASE, RechargeConfig
from value_rail.net.http_safe import PolitenessPolicy, SafeHttpClient
from value_rail.settings import Settings

LD = re.compile(r"<script[^>]*type=[\"']?application/ld\+json[\"']?[^>]*>.*?</script>", re.S | re.I)
TITLE = re.compile(r"<title[^>]*>.*?</title>", re.S | re.I)


def strip(body: bytes) -> bytes:
    html = body.decode("utf-8", errors="replace")
    t = TITLE.search(html)
    parts = ["<!doctype html><html><head>", t.group(0) if t else "", *LD.findall(html), "</head><body></body></html>"]
    return "\n".join(parts).encode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("key")
    ap.add_argument("--config", default="config/production.toml")
    ap.add_argument("--out", default="tests/fixtures/recorded")
    a = ap.parse_args()
    st = Settings(config_path=Path(a.config), _env_file=None)
    c = next(x for x in st.file_config.connectors if x.key == a.key)
    if c.kind in AGGREGATOR_KINDS:
        return record_aggregator(c, a.out)
    if c.kind == "jsonld_shop":
        cfg = JsonLdShopConfig.model_validate(c.options)
        host, skey = cfg.host, cfg.source_key
        urls = {Path(p.path.strip("/")).name + ".html": f"https://{host}{p.path}" for p in cfg.pages}
    elif c.kind == "recharge":
        cfg = RechargeConfig.model_validate(c.options)
        host, skey = "www.recharge.com", "recharge-com-de"
        urls = {f"{p.slug}.html": f"{RECHARGE_BASE}/{cfg.storefront}/{p.slug}" for p in cfg.products}
    else:
        raise SystemExit(f"connector kind {c.kind} not recordable")
    client = SafeHttpClient(source_key=skey, allowed_hosts={host}, policy=PolitenessPolicy(min_interval_s=6, jitter_s=2))
    day = datetime.now().strftime("%Y-%m-%d")
    out = Path(a.out) / f"{skey.replace('-', '_')}_{day}"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"recorded_by": f"scripts/record_fixtures.py {a.key} (SafeHttpClient, robots.txt honoured)",
            "note": "Stripped: only <title> and the schema.org ld+json blocks are kept. No cookies, no response headers, "
                    "no personal data. Box egress is US (prices/regions as served to that egress).",
            "files": {}}
    robots_url = f"https://{host}/robots.txt"
    r = client.get(robots_url, accept="text/plain")
    (out / "robots.txt").write_bytes(r.body)
    meta["files"]["robots.txt"] = {"url": robots_url, "http_status": r.status, "content_type": "text/plain",
                                   "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds")}
    for fname, url in urls.items():
        res = client.get(url)
        (out / fname).write_bytes(strip(res.body))
        meta["files"][fname] = {"url": res.url, "http_status": res.status,
                                "content_type": res.content_type or "text/html",
                                "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                                "original_body_sha256": hashlib.sha256(res.body).hexdigest(),
                                "original_body_bytes": len(res.body)}
        print(fname, res.status, len(res.body))
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print("requests:", client.request_log)
    print("wrote", out)


# ------------------------------------------------------------------------------------------- aggregators
BSV_KEEP = ("id", "name", "price", "currency", "currency_price", "quantity", "sold", "discount_percent_pub",
            "nominal_sum_pub", "auction", "is_active", "is_api_product", "productActivationRegions",
            "productActivationCountries", "productType")
CG_DROP = ("redemption_instructions", "terms", "description", "image_url")


def _sanitize_bsv(p: dict) -> dict:
    out = {k: p.get(k) for k in BSV_KEEP if k in p}
    u = p.get("user") if isinstance(p.get("user"), dict) else {}
    us = u.get("userSellers") if isinstance(u.get("userSellers"), dict) else {}
    out["productActivationCountries"] = [
        {"country": {"code_short": (c.get("country") or {}).get("code_short")}}
        for c in p.get("productActivationCountries") or [] if isinstance(c, dict)]
    out["user_id"] = pseudonym("anon", str(p.get("user_id") or u.get("username") or ""))  # no real ids/usernames
    out["user"] = {"userSellers": {"store_name": us["store_name"]}} if us.get("store_name") else {}
    return out


def _bsv_fixture(body: bytes, url: str) -> bytes:
    html = body.decode("utf-8", errors="replace")
    arr, pag = bsv_products("record", url, html)
    t = TITLE.search(html)
    flight = ('["$","div",null,{"categoryName":"recorded",' + '"initialProductsList":'
              + json.dumps([_sanitize_bsv(p) for p in arr], ensure_ascii=False) + ',"initialPagination":'
              + json.dumps(pag) + "}]")
    push = json.dumps(flight, ensure_ascii=False)
    return ("<!doctype html><html><head>" + (t.group(0) if t else "") + "</head><body><script>self.__next_f.push([1,"
            + push + "])</script></body></html>").encode()


def _section(body: bytes, start_rx: str, end_marker: str) -> bytes:
    html = body.decode("utf-8", errors="replace")
    t = TITLE.search(html)
    m = re.search(start_rx, html)
    sec = ""
    if m:
        sec = html[m.start():]
        e = sec.find(end_marker, 1)
        sec = sec[: e if e > 0 else 60_000]
    sec = re.sub(r"<script.*?</script>", "", sec, flags=re.S | re.I)
    return ("<!doctype html><html><head>" + (t.group(0) if t else "") + "</head><body>" + sec + "</body></html>").encode()


def _strip_cg(sc):
    if isinstance(sc, dict):
        return {k: _strip_cg(v) for k, v in sc.items() if k not in CG_DROP}
    if isinstance(sc, list):
        return [_strip_cg(x) for x in sc]
    return sc


def record_aggregator(c, out_root: str) -> None:
    conn = build_aggregator(c.kind, c.options)
    cfg = conn.config
    conn.client.policy = PolitenessPolicy(min_interval_s=max(6, cfg.min_interval_s), jitter_s=2)
    day = datetime.now().strftime("%Y-%m-%d")
    out = Path(out_root) / f"{cfg.source_key.replace('-', '_')}_{day}"
    out.mkdir(parents=True, exist_ok=True)
    now = lambda: datetime.now(UTC).isoformat(timespec="seconds")  # noqa: E731
    meta = {"recorded_by": f"scripts/record_fixtures.py {c.key} (SafeHttpClient, robots.txt honoured)",
            "note": "Minimal extracts only (no cookies, no response headers, no personal data: BSV usernames/user ids "
                    "replaced by hashes, only public store names kept; CoinGate: no email ever sent, long texts "
                    "dropped). Box egress is US.",
            "kind": c.kind, "files": {}}
    robots_url = f"https://{cfg.host}/robots.txt"
    r = conn.client.get(robots_url, accept="text/plain")
    (out / "robots.txt").write_bytes(r.body)
    meta["files"]["robots.txt"] = {"url": robots_url, "http_status": r.status, "content_type": "text/plain",
                                   "fetched_at_utc": now()}
    if c.kind == "coingate_mcp":
        for t in conn.targets():
            if isinstance(t, CoinGateBrand):
                tool, args = "get_gift_card", {"brand": t.brand, "country": t.country.upper()}
            else:
                assert isinstance(t, CoinGateSearch)
                tool, args = "search_gift_cards", {"category": t.category, "country": t.country.upper(),
                                                   "per_page": t.per_page, "page": 1}
            sc, msg = conn.call_tool(tool, args)
            fname = f"{t.id}.json"
            rec = {"jsonrpc": "2.0", "id": 0, "result": {"structuredContent": _strip_cg(sc), "isError": False}}
            (out / fname).write_text(json.dumps(rec, indent=1, ensure_ascii=False) + "\n")
            meta["files"][fname] = {"url": conn.endpoint, "http_status": msg["_status"], "content_type": "application/json",
                                    "mcp_tool": tool, "mcp_arguments": args, "fetched_at_utc": now(),
                                    "original_body_sha256": msg["_body_sha256"], "original_body_bytes": msg["_body_bytes"]}
            print(fname, msg["_status"], msg["_body_bytes"])
    else:
        for t in conn.targets():
            if c.kind == "gcw_hotdeals":
                url = f"https://{cfg.host}{cfg.path}"
            else:
                assert isinstance(t, (BsvPage, CardBearPage))
                url = f"https://{cfg.host}{t.path}"
            res = conn.client.get(url)
            if c.kind == "bsv_list":
                body = _bsv_fixture(res.body, res.url)
            elif c.kind == "cardbear_html":
                body = _section(res.body, r'<div\s+role="table"', "<h2")
            else:
                body = _section(res.body, r"Filter by Brand", "</table>")
            fname = f"{t.id}.html"
            (out / fname).write_bytes(body)
            meta["files"][fname] = {"url": res.url, "http_status": res.status, "content_type": res.content_type or "text/html",
                                    "fetched_at_utc": now(), "original_body_sha256": hashlib.sha256(res.body).hexdigest(),
                                    "original_body_bytes": len(res.body)}
            print(fname, res.status, len(res.body), "->", len(body))
    (out / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    print("requests:", conn.client.request_log)
    print("wrote", out)


if __name__ == "__main__":
    main()
