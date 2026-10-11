"""Operator-reviewed quote intake. No network, purchases or synthetic promotion.

Artifact hashes prove which document was reviewed, not that its issuer is honest.
The named real operator remains responsible for authenticity and executability.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from .connectors.base import DiscoveryItem, NormalizedOffer, QuoteBundle, SourceSpec
from .domain.entities import QuantityObservation
from .domain.identity import ProductIdentity
from .evidence import EvidenceDraft
from .storage.orm import ProductRow, RouteEvaluationRow
from .storage.repo import active_rule_version, latest_evaluation_for, rule_params_of
from .valuation.models import CheckoutQuoteInput, ExitQuoteInput, FeeComponent, RouteInputs
from .worker.scan import _Fetched, _operator, _persist_item


class CapturedQuote(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: ProductIdentity
    source_url: HttpUrl
    source_name: str = Field(min_length=1, max_length=200)
    unit_price: Decimal = Field(gt=0, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    quantity: int = Field(gt=0, strict=True)
    captured_at: datetime
    valid_until: datetime
    firm: Literal[True]
    fees_complete: Literal[True]
    fees: list[FeeComponent]
    artifact: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_capture(self):
        for dt in (self.captured_at, self.valid_until):
            if dt.tzinfo is None or dt.utcoffset() is None:
                raise ValueError("quote timestamps require an explicit timezone")
        if self.valid_until <= self.captured_at:
            raise ValueError("valid_until must be later than captured_at")
        url = urlsplit(str(self.source_url))
        if url.scheme != "https" or url.username or url.password:
            raise ValueError("quote origin must be HTTPS without embedded credentials")
        for fee in self.fees:
            if fee.amount != "unknown" and fee.amount < 0:
                raise ValueError("negative fees cannot establish quote costs")
            if fee.cap_per_unit is not None and fee.cap_per_unit < 0:
                raise ValueError("negative fee caps are invalid")
        return self


class QuoteImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    evaluation_id: int = Field(gt=0, strict=True)
    reviewed_by: str = Field(min_length=1)
    checkout: CapturedQuote
    exit: CapturedQuote | None = None


def load_quote_import(path: Path, now: datetime) -> QuoteImport:
    if path.stat().st_size > 1_000_000:
        raise ValueError("quote manifest exceeds 1 MB")
    document = QuoteImport.model_validate(json.loads(path.read_text(), parse_float=Decimal))
    base = path.resolve().parent
    for q in (document.checkout, document.exit):
        if q is None:
            continue
        if q.captured_at > now:
            raise ValueError("future quote capture is not evidence")
        relative = Path(q.artifact)
        artifact = (base / relative).resolve()
        if relative.is_absolute() or not artifact.is_relative_to(base):
            raise ValueError("artifact must be inside the manifest directory")
        if artifact.stat().st_size > 10_000_000:
            raise ValueError("quote artifact exceeds 10 MB")
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != q.artifact_sha256:
            raise ValueError("artifact hash mismatch")
    return document


def import_quotes(ctx, path: Path, now: datetime) -> dict:
    document = load_quote_import(path, now)
    with ctx.session_factory.begin() as s:
        base = s.get(RouteEvaluationRow, document.evaluation_id)
        if base is None:
            raise ValueError("evaluation does not exist")
        previous = RouteInputs.model_validate(base.inputs)
        if base.is_synthetic or previous.is_synthetic:
            raise ValueError("cannot attach real quotes to synthetic evaluations")
        latest = latest_evaluation_for(s, base.route_key)
        if latest.id != base.id:
            raise ValueError("base evaluation is no longer latest; review the current route")
        cfg = ctx.settings.file_config.operator
        operator = _operator(s, cfg.name if cfg else None, synthetic=False)
        if cfg is None or operator is None or document.reviewed_by != operator.name:
            raise ValueError("quote reviewer must be the configured real operator")
        for q in (document.checkout, document.exit):
            if q and previous.product.mismatches(q.identity):
                raise ValueError("quote product identity does not match the route")
        product = s.get(ProductRow, base.product_id) if base.product_id else None
        if product is None:
            raise ValueError("evaluation has no stored product identity")

        def bundle(q, kind):
            if q is None:
                return None
            origin = urlsplit(str(q.source_url)).hostname
            key = f"manual-{kind}:" + hashlib.sha256(origin.encode()).hexdigest()[:16]
            source = SourceSpec(key=key, name=q.source_name,
                                kind="direct_seller" if kind == "checkout" else "exit_venue",
                                role="price_basis" if kind == "checkout" else "exit")
            # Fees bind to the same artifact as the reviewed quote, never arbitrary refs.
            fees = [f.model_copy(update={"evidence_ref": "sha256:" + q.artifact_sha256}) for f in q.fees]
            values = dict(quote_ref="pending", identity=q.identity, unit_price=q.unit_price, currency=q.currency,
                          fees=fees, captured_at=q.captured_at, valid_until=q.valid_until)
            quote = (CheckoutQuoteInput(source_key=key, quantity_confirmed=q.quantity, **values) if kind == "checkout"
                     else ExitQuoteInput(venue_key=key, depth_quantity=q.quantity, **values))
            draft = EvidenceDraft(kind=f"{kind}_quote", source_key=key, captured_at=q.captured_at,
                                  scope="operator-reviewed", summary=f"Quote reviewed by {document.reviewed_by}",
                                  payload={"source_url": str(q.source_url), "reviewed_by": document.reviewed_by,
                                           "artifact_sha256": q.artifact_sha256, "artifact": q.artifact,
                                           "quote": q.model_dump(mode="json")})
            return QuoteBundle(source=source, quote=quote, evidence=[draft])

        checkout = bundle(document.checkout, "checkout")
        exit_ = bundle(document.exit, "exit")
        q = checkout.quote
        offer = NormalizedOffer(source=checkout.source, identity=q.identity, unit_price=q.unit_price,
                                currency=q.currency, price_text_raw=str(q.unit_price), price_includes_fees=False,
                                fees=q.fees, advertised_quantity=QuantityObservation(),
                                checkout_confirmed_quantity=QuantityObservation(value=q.quantity_confirmed,
                                    observed_at=q.captured_at, scope="operator-reviewed-checkout"),
                                purchased_quantity=QuantityObservation(), captured_at=q.captured_at,
                                evidence=checkout.evidence, raw={"operator_reviewed": True}, is_synthetic=False)
        # Public listing scans must not overwrite a separately reviewed executable route.
        reviewed_key = base.route_key if base.route_key.startswith("reviewed:") else "reviewed:" + base.route_key
        item = DiscoveryItem(route_key=reviewed_key, product=previous.product, product_family=product.product_family,
                             sources=[checkout.source] + ([exit_.source] if exit_ else []),
                             prerequisites=[p.name for p in previous.prerequisites], is_synthetic=False)
        from .catalog import in_scope
        if not in_scope(item, ctx.settings):
            raise ValueError("route is outside the configured liquid-value scope")
        rule = active_rule_version(s, now)
        if rule is None:
            raise ValueError("no active valuation rules")
        # Persist new rows atomically; never overwrite the source evaluation or capture times.
        ev, result, alerted = _persist_item(s, _Fetched(item=item, offers=[offer], checkout=checkout, exit=exit_),
            scan_id=None, rv_id=rule.id, params=rule_params_of(rule), operator=operator, settings=ctx.settings, now=now)
        return {"evaluation_id": ev.id, "status": result.status.value, "profit_eur": str(result.profit_eur),
                "missing_evidence": result.missing_evidence, "block_reasons": result.block_reasons,
                "alert_enqueued": alerted, "provenance": "operator_reviewed_artifacts"}
