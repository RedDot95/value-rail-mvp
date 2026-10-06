"""Research catalogue for liquid-value candidates, never proof of liquidity.

Only route-specific checkout/exit evidence can establish a profitable route.
Aliases classify products for scope; they never merge product identities.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from importlib.resources import files


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", value))


@lru_cache(maxsize=1)
def instruments() -> list[dict]:
    return json.loads(files("value_rail").joinpath("data/instruments.json").read_text(encoding="utf-8"))["instruments"]


EXCLUDED = ("steam", "playstation", "psn", "xbox", "nintendo", "razer", "roblox", "minecraft",
            "fortnite", "riot games", "valorant", "league of legends", "battle net", "battlenet",
            "netflix", "spotify", "disney", "dazn", "google play", "itunes", "app store",
            "fansly", "onlyfans", "patreon", "twitch", "discord", "chaturbate", "midjourney",
            "facebook ads", "fiverr", "buy me a coffee", "buymeacoffee", "gocash game card",
            "cherry credits", "garena")


def resolve_instrument(*values: str) -> dict | None:
    texts = [" " + normalized(v) + " " for v in values if v]
    if any(" " + normalized(alias) + " " in t for alias in EXCLUDED for t in texts):
        return None
    matches = []
    for item in instruments():
        for alias in [item["key"], *item["aliases"]]:
            term = normalized(alias)
            if any(" " + term + " " in t for t in texts):
                matches.append((len(term), item))
    return max(matches, key=lambda x: x[0])[1] if matches else None


def instrument_for_item(item):
    return resolve_instrument(item.product_family, item.product.redemption_program,
                              str(item.meta.get("title", "")))


def in_scope(item, settings) -> bool:
    if item.is_synthetic or not settings.file_config.scope.enabled:
        return True
    if item.meta.get("page_error"):
        return True  # never filter out a disturbance
    return instrument_for_item(item) is not None
