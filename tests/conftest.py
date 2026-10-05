"""Shared offline test fixtures. Every DB is a fresh temp SQLite file migrated with Alembic."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from value_rail.domain.entities import QuantityObservation
from value_rail.domain.identity import ProductIdentity
from value_rail.services import AppContext
from value_rail.settings import Settings
from value_rail.valuation.models import (CheckoutQuoteInput, ExitQuoteInput, FeeComponent, OfferInput,
                                         Prerequisite, RouteInputs, RuleParams)

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
NOW = datetime(2026, 10, 4, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def now() -> datetime:
    return NOW


def make_settings(tmp_path: Path, fixtures_dir: Path = FIXTURES, **kw) -> Settings:
    return Settings(db_url=f"sqlite:///{tmp_path / 'test.db'}", config_path=REPO / "config" / "default.toml",
                    fixtures_dir=fixtures_dir, migrations_dir=REPO / "migrations", _env_file=None, **kw)


@pytest.fixture
def ctx(tmp_path: Path):
    c = AppContext(make_settings(tmp_path))
    c.settings.alert_log_file = str(tmp_path / "alerts.log")
    c.init_db(now=NOW)
    yield c
    c.dispose()


@pytest.fixture
def scenario_dir(tmp_path: Path) -> Path:
    """Writable copy of the fixture tree for tests that mutate scenarios."""
    d = tmp_path / "fixtures"
    shutil.copytree(FIXTURES, d)
    return d


def write_scenario(d: Path, data: dict) -> None:
    (d / "scenarios" / f"{data['scenario_id']}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_scenario(name: str) -> dict:
    return json.loads((FIXTURES / "scenarios" / f"{name}.json").read_text(encoding="utf-8"))


# ---------- pure-engine builders ----------

PRODUCT = ProductIdentity(face_value=Decimal("100"), face_currency="EUR", region="DE", variant="digital-code",
                          seller="SYNTHETIC-Direct-A", redemption_program="SYNTHETIC-Program-A")
RULE = RuleParams(label="test-v1")


def offer(unit="45.00", *, role="price_basis", currency="EUR", identity=PRODUCT, fees=(), includes=True,
          ref="offer_snapshot:1", captured=NOW, adv="unknown", confirmed="unknown", purchased="unknown") -> OfferInput:
    return OfferInput(offer_ref=ref, source_key="synthetic-src", source_role=role, identity=identity,
                      unit_price=unit if unit == "unknown" else Decimal(unit), currency=currency,
                      price_includes_fees=includes, fees=list(fees), captured_at=captured,
                      advertised_quantity=QuantityObservation(value=adv, observed_at=captured, scope="listing"),
                      checkout_confirmed_quantity=QuantityObservation(value=confirmed, scope="checkout_session"),
                      purchased_quantity=QuantityObservation(value=purchased, scope="historical_purchase"))


def checkout(unit="45.00", qty=1, *, identity=PRODUCT, fees=(), captured=NOW, currency="EUR") -> CheckoutQuoteInput:
    return CheckoutQuoteInput(quote_ref="quote:1", source_key="synthetic-src", identity=identity,
                              unit_price=Decimal(unit), currency=currency, quantity_confirmed=qty, fees=list(fees),
                              captured_at=captured)


def exit_quote(unit="100.00", depth=1, *, identity=PRODUCT, fees=(), captured=NOW, currency="EUR") -> ExitQuoteInput:
    return ExitQuoteInput(quote_ref="quote:2", venue_key="synthetic-exit", identity=identity,
                          unit_price=Decimal(unit), currency=currency, depth_quantity=depth, fees=list(fees),
                          captured_at=captured)


def inputs(*, offers=None, cq=None, eq=None, prereqs=(), product=PRODUCT, at=NOW) -> RouteInputs:
    return RouteInputs(route_key="synthetic:test", product=product, offers=offers if offers is not None else [offer()],
                       checkout_quote=cq, exit_quote=eq,
                       prerequisites=[Prerequisite(name=n, status=s) for n, s in prereqs], evaluated_at=at,
                       is_synthetic=True)


def fee(name, kind, amount, **kw) -> FeeComponent:
    return FeeComponent(name=name, kind=kind, amount=amount if amount == "unknown" else Decimal(amount), **kw)
