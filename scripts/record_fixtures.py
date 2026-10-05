"""Record stripped, dated offline fixtures for a live connector (uses the same SafeHttpClient: robots.txt,
>=5 s/host + jitter, allowlist). Keeps only <title> and schema.org ld+json blocks - no cookies, no headers,
no personal data. Usage: python scripts/record_fixtures.py <connector-key> [--config config/production.toml]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

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


if __name__ == "__main__":
    main()
