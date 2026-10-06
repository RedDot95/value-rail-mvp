"""Safety overlay: how inferred signals may affect what the operator SEES. Monotone by construction.

- An `advisory_block` signal (restriction_risk >= threshold) turns the ADVISORY status into `blocked`.
- Nothing here can produce `price_find`/`verified_route` or remove a block: the advisory status is either the
  deterministic status or `blocked`.
- The deterministic RouteEvaluation (status, Decimal outputs) and the alert outbox are never modified; the
  overlay is computed at read time for display/triage only. It never triggers a fetch retry, a different
  route, a bypass, a purchase or any account action.
"""

from __future__ import annotations

from typing import Iterable

ADVISORY_BLOCK = "advisory_block"
SUSPECTED_BLOCK_PAGE = "suspected_block_page"
BLOCKED = "blocked"


def advisory_status(deterministic_status: str, signals: Iterable[str]) -> str:
    return BLOCKED if ADVISORY_BLOCK in set(signals) else deterministic_status


def advisory_view(deterministic_status: str, signals: Iterable[str]) -> dict[str, object]:
    sig = set(signals)
    adv = advisory_status(deterministic_status, sig)
    return {"deterministic_status": deterministic_status, "advisory_status": adv,
            "inferred_block": ADVISORY_BLOCK in sig, "changed": adv != deterministic_status,
            "suspected_block_page": SUSPECTED_BLOCK_PAGE in sig}
