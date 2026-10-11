"""Application context: settings + DB engine + session factory + seeding."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .connectors.fixture import load_operator_profiles
from .domain.timeutil import utcnow
from .settings import Settings, get_settings
from .storage.db import make_engine, make_session_factory, migrate
from .storage.repo import active_rule_version, ensure_rule_version, rule_version_by_label, upsert_operator_profile
from .valuation.models import RuleParams

log = logging.getLogger("value_rail")


@dataclass
class AppContext:
    settings: Settings = field(default_factory=get_settings)
    engine: Engine = field(init=False)
    session_factory: sessionmaker[Session] = field(init=False)

    def __post_init__(self) -> None:
        self.engine = make_engine(self.settings.database_url)
        self.session_factory = make_session_factory(self.engine)

    def rule_params_from_config(self) -> RuleParams:
        return RuleParams.model_validate(self.settings.file_config.rules.model_dump())

    def init_db(self, *, seed: bool = True, now: datetime | None = None) -> None:
        migrate(self.settings)
        if seed:
            self.seed(now=now)

    def seed(self, now: datetime | None = None) -> None:
        now = now or utcnow()
        with self.session_factory.begin() as s:
            cfg_params = self.rule_params_from_config()
            # New config label (e.g. Delivery 2 exit rules) -> new immutable RuleVersion; versions added via
            # `rules add` are never overwritten because the config label already exists afterwards.
            if active_rule_version(s, now) is None or rule_version_by_label(s, cfg_params.label) is None:
                ensure_rule_version(s, cfg_params, now=now, notes="seeded from config/default.toml")
            for p in load_operator_profiles(Path(self.settings.fixtures_dir)):
                upsert_operator_profile(s, name=p["name"], region=p.get("region", "unknown"),
                                        capabilities=p.get("capabilities", {}),
                                        max_budget_eur=p.get("max_budget_eur", "unknown"),
                                        is_synthetic=True)
            operator = self.settings.file_config.operator
            if operator is not None:
                capabilities = {name: proof.status.value for name, proof in operator.capabilities.items()}
                capabilities["_evidence"] = {name: proof.evidence_ref for name, proof in operator.capabilities.items()}
                upsert_operator_profile(s, name=operator.name, region=operator.region,
                                        capabilities=capabilities, max_budget_eur=operator.max_budget_eur,
                                        is_synthetic=False)

    def dispose(self) -> None:
        self.engine.dispose()
