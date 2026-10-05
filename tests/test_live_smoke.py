"""LIVE smoke test (network). Excluded by default; run explicitly: `pytest -m live`.

Any outcome is acceptable as long as it is EXPLICIT: offers parsed, or a distinct FetchError
(robots/403/429/parser break/...). Silent "zero offers" is the only failure.
"""

from __future__ import annotations

import pytest

from value_rail.connectors.recharge import RechargeConnector
from value_rail.domain.timeutil import utcnow
from value_rail.net.errors import FetchError


@pytest.mark.live
def test_live_recharge_discovery_is_explicit():
    c = RechargeConnector()
    items = c.discovery(utcnow())
    assert items, "discovery must never silently return nothing"
    for it in items:
        if it.meta.get("page_error"):
            with pytest.raises(FetchError):
                c.offer_fetch(it, utcnow())
        else:
            assert it.product.seller == "recharge.com" and it.product.face_value != "unknown"
