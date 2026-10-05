"""Pluggable alert sinks. Delivery 1 ships LogAlertSink only (structured JSON log lines)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger("value_rail.alerts")


class AlertSink(Protocol):
    name: str

    def send(self, payload: dict[str, Any]) -> None:
        """Deliver one alert. Raise on failure (the dispatcher retries)."""


class LogAlertSink:
    name = "log"

    def __init__(self, log_file: str | Path | None = None) -> None:
        self.log_file = Path(log_file) if log_file else None

    def send(self, payload: dict[str, Any]) -> None:
        line = json.dumps({"type": "value_rail.alert", **payload}, sort_keys=True, default=str)
        log.info(line)
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_file, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()


class MemorySink:
    """Test helper; optionally fails the first N sends."""

    name = "memory"

    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail_times = fail_times

    def send(self, payload: dict[str, Any]) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("simulated sink failure")
        self.sent.append(payload)


def build_sink(name: str, log_file: str | None = None) -> AlertSink:
    if name == "log":
        return LogAlertSink(log_file)
    raise ValueError(f"unknown alert sink {name!r} (Delivery 1 supports: log)")
