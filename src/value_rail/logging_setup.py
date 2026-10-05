from __future__ import annotations

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(h, "_value_rail", False) for h in root.handlers):
        return
    h = logging.StreamHandler(sys.stderr)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    h._value_rail = True  # type: ignore[attr-defined]
    root.addHandler(h)
    root.setLevel(level.upper())
