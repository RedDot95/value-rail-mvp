"""Pluggable alert sinks: LogAlertSink (default), TelegramAlertSink (opt-in), CompositeSink."""

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


class AlertDeliveryError(RuntimeError):
    """Sanitised sink error (never contains tokens/URLs with secrets)."""


TELEGRAM_HOST = "api.telegram.org"
TELEGRAM_MAX_TEXT = 4096  # Bot API sendMessage text limit (core.telegram.org/bots/api#sendmessage)


class TelegramAlertSink:
    """Telegram Bot API `sendMessage` (POST https://api.telegram.org/bot<token>/sendMessage).

    Disabled unless a bot token AND a chat id are configured. Never constructed in tests with a real
    transport. The token never appears in errors, logs or the outbox (errors are sanitised).
    SYNTHETIC alerts are skipped by default (they are still written by the log sink).
    """

    name = "telegram"

    def __init__(self, token: str, chat_id: str, *, send_synthetic: bool = False, client=None) -> None:
        token, chat_id = (token or "").strip(), (chat_id or "").strip()
        if not token or not chat_id:
            raise ValueError("Telegram sink needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID; refusing to build it")
        self._token = token
        self.chat_id = chat_id
        self.send_synthetic = send_synthetic
        if client is None:
            from ..net.http_safe import PolitenessPolicy, SafeHttpClient
            client = SafeHttpClient(source_key="telegram", allowed_hosts={TELEGRAM_HOST}, respect_robots=False,
                                    policy=PolitenessPolicy(min_interval_s=1.0, jitter_s=0.2, max_retries=1))
        self.client = client
        self.skipped: list[str] = []

    def __repr__(self) -> str:  # never leak the token
        return f"TelegramAlertSink(chat_id={self.chat_id!r}, token=***)"

    @staticmethod
    def format_text(payload: dict[str, Any]) -> str:
        lines = [("[SYNTHETISCH] " if payload.get("synthetic") else "") + str(payload.get("summary_de", "")),
                 f"Route: {payload.get('route_key')}", f"Status: {payload.get('status_de')} ({payload.get('reason')})",
                 f"Bewertung #{payload.get('route_evaluation_id')} - {payload.get('evaluated_at_utc')} UTC",
                 f"Event: {payload.get('event_id')}"]
        if payload.get("screening"):
            x = payload["screening"]
            lines = [str(payload["summary_de"]), f"Händler: {x['seller']} · Region: {x['region']}",
                     f"Angezeigter Bestand: {payload.get('advertised_quantity', 'unknown')}",
                     f"Beobachtet: {x['captured_at']}"]
            if x.get("valid_until"):
                lines.append(f"Gültig bis: {x["valid_until"]}")
            if x.get("listing_url"):
                lines.append(x["listing_url"])
        missing = payload.get("missing_evidence") or []
        if missing:
            lines.append("Fehlende Nachweise: " + ", ".join(missing))
        return "\n".join(lines)[:TELEGRAM_MAX_TEXT]

    def send(self, payload: dict[str, Any]) -> None:
        if payload.get("synthetic") and not self.send_synthetic:
            self.skipped.append(str(payload.get("event_id")))
            return
        body = json.dumps({"chat_id": self.chat_id, "text": self.format_text(payload),
                           "disable_web_page_preview": True}).encode()
        url = f"https://{TELEGRAM_HOST}/bot{self._token}/sendMessage"
        from ..net.errors import FetchError
        try:
            res = self.client.post_json(url, body)
        except FetchError as exc:
            raise AlertDeliveryError(f"telegram send failed: {exc.code} (HTTP {exc.http_status})") from None
        try:
            data = json.loads(res.body or b"{}")
        except ValueError:
            data = {}
        if res.status != 200 or not data.get("ok"):
            desc = str(data.get("description", ""))[:200].replace(self._token, "***")
            raise AlertDeliveryError(f"telegram API error HTTP {res.status}: {desc}")


class CompositeSink:
    """Fan-out. Remembers per-process which sink already delivered an event so a retry after a partial
    failure does not resend to the sinks that succeeded."""

    def __init__(self, sinks: list[AlertSink]) -> None:
        self.sinks = sinks
        self.name = "+".join(x.name for x in sinks)
        self._done: set[tuple[str, str]] = set()

    def send(self, payload: dict[str, Any]) -> None:
        errors = []
        for sk in self.sinks:
            key = (sk.name, str(payload.get("event_id")))
            if key in self._done:
                continue
            try:
                sk.send(payload)
                self._done.add(key)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sk.name}: {exc}")
        if errors:
            raise AlertDeliveryError("; ".join(errors))


def build_sink(name: str, log_file: str | None = None, *, telegram_token: str = "", telegram_chat_id: str = "",
               telegram_send_synthetic: bool = False) -> AlertSink:
    names = [n.strip() for n in name.split(",") if n.strip()]
    sinks: list[AlertSink] = []
    for n in names:
        if n == "log":
            sinks.append(LogAlertSink(log_file))
        elif n == "telegram":
            if not (telegram_token.strip() and telegram_chat_id.strip()):
                log.warning("alerts.sink lists 'telegram' but TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID are not set - "
                            "Telegram stays DISABLED")
                continue
            sinks.append(TelegramAlertSink(telegram_token, telegram_chat_id, send_synthetic=telegram_send_synthetic))
        else:
            raise ValueError(f"unknown alert sink {n!r} (supported: log, telegram)")
    if not sinks:
        sinks.append(LogAlertSink(log_file))
    return sinks[0] if len(sinks) == 1 else CompositeSink(sinks)


def build_sink_from_settings(settings) -> AlertSink:
    cfg = settings.file_config.alerts
    return build_sink(cfg.sink, settings.effective_alert_log_file, telegram_token=settings.telegram_bot_token,
                      telegram_chat_id=settings.telegram_chat_id, telegram_send_synthetic=cfg.telegram_send_synthetic)
