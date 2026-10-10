from __future__ import annotations

import json

import pytest

from value_rail.connectors.fixture import FixtureConnector
from value_rail.connectors.registry import build_connectors, describe_connectors

from .conftest import FIXTURES, make_settings


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
    assert set(rows) == {"fixture"}
