from __future__ import annotations

import json

from typer.testing import CliRunner

from value_rail.cli import app

from .conftest import FIXTURES, REPO


def _env(tmp_path):
    return {"VALUE_RAIL_DB_PATH": str(tmp_path / "cli.db"), "VALUE_RAIL_FIXTURES_DIR": str(FIXTURES),
            "VALUE_RAIL_CONFIG_PATH": str(REPO / "config" / "default.toml"),
            "VALUE_RAIL_MIGRATIONS_DIR": str(REPO / "migrations"), "VALUE_RAIL_DB_URL": ""}


def test_cli_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # alerts.log lands in tmp
    r = CliRunner()
    env = _env(tmp_path)
    assert r.invoke(app, ["init-db"], env=env).exit_code == 0
    res = r.invoke(app, ["load-fixtures"], env=env)
    assert res.exit_code == 0, res.output
    assert "5 neue Alerts" in res.output and "Verifizierte Route" in res.output
    res2 = r.invoke(app, ["load-fixtures"], env=env)
    assert "0 neue Alerts" in res2.output
    lines = (tmp_path / "data" / "alerts.log").read_text().splitlines()
    assert len(lines) == 5
    res3 = r.invoke(app, ["load-fixtures", "--down", "synthetic-paysafe-reseller"], env=env)
    assert "degraded" in res3.output
    diag = r.invoke(app, ["diagnose"], env=env)
    assert diag.exit_code == 0
    info = json.loads(diag.stdout)
    assert info["live_scanning"] is False and info["counts"]["route_evaluations"] == 29
    assert r.invoke(app, ["replay", "4"], env=env).exit_code == 0
    assert r.invoke(app, ["evaluations"], env=env).exit_code == 0
    assert r.invoke(app, ["rules", "add", "--label", "synthetic-v2", "--param", "price_find_min_discount=0.30"],
                    env=env).exit_code == 0
