from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import select, text

from value_rail.connectors.fixture import FixtureConnector
from value_rail.domain.entities import QuantityObservation
from value_rail.domain.identity import ProductIdentity
from value_rail.storage.orm import AssetRow, Base, ImmutableRecordError, OfferSnapshotRow, RouteEvaluationRow
from value_rail.storage.repo import (correct_offer_snapshot, get_or_create_product, insert_offer_snapshot,
                                     upsert_asset, upsert_source)
from value_rail.worker.scan import run_scan

from .conftest import FIXTURES


def test_migration_matches_models(ctx):
    with ctx.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []


def _snapshot(s, now):
    src = upsert_source(s, key="synthetic-src", name="SYNTHETIC", kind="direct_seller", role="price_basis", is_synthetic=True)
    p = get_or_create_product(s, ProductIdentity(face_value=Decimal("10"), face_currency="EUR", region="DE", variant="v",
                                                 seller="s", redemption_program="r"), family="x", now=now, is_synthetic=True)
    return insert_offer_snapshot(s, source=src, product=p, scan_run_id=None, route_key="synthetic:t", captured_at=now,
                                 price_amount=Decimal("1.10"), price_currency="EUR", price_text_raw="1,10 €",
                                 price_includes_fees=True, fees=[], advertised=QuantityObservation(value=5, observed_at=now, scope="listing"),
                                 checkout_confirmed=QuantityObservation(), purchased=QuantityObservation(), raw={},
                                 is_synthetic=True)


def test_snapshots_immutable_orm_guard_and_db_trigger(ctx, now):
    with ctx.session_factory.begin() as s:
        snap_id = _snapshot(s, now).id
    with pytest.raises(ImmutableRecordError):
        with ctx.session_factory.begin() as s:
            s.get(OfferSnapshotRow, snap_id).price_amount = Decimal("0.50")
    # even raw SQL is refused by the SQLite trigger
    with pytest.raises(Exception, match="immutable"):
        with ctx.engine.begin() as conn:
            conn.execute(text("UPDATE offer_snapshots SET price_amount='0.5' WHERE id=:i"), {"i": snap_id})
    with pytest.raises(Exception, match="immutable"):
        with ctx.engine.begin() as conn:
            conn.execute(text("DELETE FROM offer_snapshots WHERE id=:i"), {"i": snap_id})


def test_correction_creates_new_version(ctx, now):
    with ctx.session_factory.begin() as s:
        snap_id = _snapshot(s, now).id
    with ctx.session_factory.begin() as s:
        v2 = correct_offer_snapshot(s, snap_id, reason="SYNTHETIC price typo", price_amount=Decimal("1.15"))
        v2_id = v2.id
    with ctx.session_factory() as s:
        old, new = s.get(OfferSnapshotRow, snap_id), s.get(OfferSnapshotRow, v2_id)
        assert old.price_amount == Decimal("1.10") and old.version == 1
        assert new.price_amount == Decimal("1.15") and new.version == 2 and new.supersedes_id == snap_id


def test_decimal_and_utc_roundtrip_exact(ctx, now):
    with ctx.session_factory.begin() as s:
        snap_id = _snapshot(s, now).id
    raw = sqlite3.connect(ctx.settings.database_url.removeprefix("sqlite:///")).execute(
        "select price_amount, captured_at from offer_snapshots where id=?", (snap_id,)).fetchone()
    assert raw[0] == "1.10"  # TEXT, not float
    assert raw[1].endswith("+00:00")
    with ctx.session_factory() as s:
        row = s.get(OfferSnapshotRow, snap_id)
        assert row.price_amount == Decimal("1.10") and row.captured_at == now


def test_naive_datetime_rejected(ctx, now):
    with pytest.raises(Exception, match="naive"):
        with ctx.session_factory.begin() as s:
            _snapshot(s, now.replace(tzinfo=None))


# 7 (storage side)
def test_case07_assets_merge_only_on_chain_and_contract(ctx):
    with ctx.session_factory.begin() as s:
        a = upsert_asset(s, symbol="USDX", chain="synthetic-chain-a", contract_address="0xAAA", is_synthetic=True)
        b = upsert_asset(s, symbol="USDX", chain="synthetic-chain-b", contract_address="0xAAA", is_synthetic=True)
        c = upsert_asset(s, symbol="USDX", chain="synthetic-chain-a", contract_address="0xBBB", is_synthetic=True)
        a2 = upsert_asset(s, symbol="USDX.e", chain="SYNTHETIC-CHAIN-A", contract_address="0xaaa", is_synthetic=True)
        assert len({a.id, b.id, c.id}) == 3
        assert a2.id == a.id
        assert s.scalar(select(AssetRow).where(AssetRow.id == a.id)).symbol == "USDX"
        with pytest.raises(ValueError):
            upsert_asset(s, symbol="USDX", chain="unknown", contract_address="0xAAA")


def test_evaluation_rows_are_immutable(ctx, now):
    run_scan(ctx.session_factory, FixtureConnector(FIXTURES), ctx.settings, now)
    with pytest.raises(ImmutableRecordError):
        with ctx.session_factory.begin() as s:
            ev = s.scalars(select(RouteEvaluationRow)).first()
            ev.status = "verified_route"
