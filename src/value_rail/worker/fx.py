"""Public ECB daily reference rates for cross-currency listing screening only."""
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from xml.etree import ElementTree

from ..valuation.models import FxRate

URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-daily.xml"
_cached: tuple[datetime, list[FxRate]] | None = None


def parse_rates(body: bytes) -> list[FxRate]:
    root = ElementTree.fromstring(body)
    day = next(x for x in root.iter() if "time" in x.attrib)
    captured = datetime.fromisoformat(day.attrib["time"]).replace(tzinfo=UTC)
    ref = f"{URL}#sha256={sha256(body).hexdigest()}"
    rates = []
    for node in day:
        rate = Decimal(node.attrib["rate"])
        if not rate.is_finite() or rate <= 0:
            raise ValueError("invalid ECB exchange rate")
        rates.append(FxRate(currency=node.attrib["currency"], rate_to_eur=Decimal(1) / rate,
                            captured_at=captured, quote_ref=ref))
    if not rates:
        raise ValueError("empty ECB rate set")
    return rates


def reference_rates(now: datetime) -> list[FxRate]:
    global _cached
    if _cached and 0 <= (now - _cached[0]).total_seconds() < 3600:
        return _cached[1]
    # Cache failed attempts too: do not retry this auxiliary source once per listing.
    _cached = now, []
    from ..net.http_safe import SafeHttpClient, PolitenessPolicy
    client = SafeHttpClient(source_key="ecb-reference-rates", allowed_hosts={"www.ecb.europa.eu"},
                            policy=PolitenessPolicy(min_interval_s=5, jitter_s=1, max_retries=1))
    response = client.get(URL, accept="application/xml")
    if response.status != 200:
        raise ValueError("ECB response not successful")
    rates = parse_rates(response.body)
    _cached = now, rates
    return rates
