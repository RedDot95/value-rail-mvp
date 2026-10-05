from __future__ import annotations

import json

import pytest

from value_rail.connectors.fixture import FixtureConnector
from value_rail.connectors.placeholders import bitsa_placeholder, paysafe_placeholder
from value_rail.connectors.registry import build_connectors, describe_connectors

from .conftest import FIXTURES, make_settings


@pytest.mark.parametrize("factory", [bitsa_placeholder, paysafe_placeholder])
def test_placeholders_claim_nothing(factory, now):
    c = factory()
    caps = c.capabilities()
    assert not any([caps.discovery, caps.offer_fetch, caps.normalize, caps.checkout_quote, caps.exit_quote,
                    caps.live_network])
    with pytest.raises(NotImplementedError):
        c.discovery(now)


def test_fixture_connector_offline_and_synthetic(now):
    caps = FixtureConnector(FIXTURES).capabilities()
    assert caps.synthetic and not caps.live_network


def test_unmarked_fixture_rejected(tmp_path, now):
    (tmp_path / "scenarios").mkdir()
    (tmp_path / "scenarios" / "x.json").write_text(json.dumps({"scenario_id": "x"}))
    with pytest.raises(ValueError, match="synthetic"):
        FixtureConnector(tmp_path).discovery(now)


def test_registry_builds_only_fixture(tmp_path):
    st = make_settings(tmp_path)
    cs = build_connectors(st)
    assert [c.key for c in cs] == ["fixture"]
    rows = {r["key"]: r for r in describe_connectors(st)}
    assert rows["bitsa"]["enabled"] is False and rows["paysafe"]["enabled"] is False
