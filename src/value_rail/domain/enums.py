from __future__ import annotations

from enum import StrEnum


class RouteStatus(StrEnum):
    PRICE_FIND = "price_find"          # Preisfund (research)
    VERIFIED_ROUTE = "verified_route"  # Verifizierte Route
    BLOCKED = "blocked"
    EXPIRED = "expired"
    EXECUTED = "executed"
    FAILED = "failed"
    # Documented addition (docs/decisions.md D-07): evaluation stored for audit/replay
    # but neither threshold reached. Never alerted, never shown as a hit.
    NO_SIGNAL = "no_signal"


STATUS_LABEL_DE = {
    RouteStatus.PRICE_FIND: "Preisfund",
    RouteStatus.VERIFIED_ROUTE: "Verifizierte Route",
    RouteStatus.BLOCKED: "Blockiert",
    RouteStatus.EXPIRED: "Abgelaufen",
    RouteStatus.EXECUTED: "Ausgefuehrt",
    RouteStatus.FAILED: "Fehlgeschlagen",
    RouteStatus.NO_SIGNAL: "Kein Signal",
}


class SourceRole(StrEnum):
    PRICE_BASIS = "price_basis"        # direct seller; may serve as purchase price evidence
    DISCOVERY_ONLY = "discovery_only"  # aggregator; leads only, never a price basis
    EXIT = "exit"                      # exit venue (sell side)


class SourceKind(StrEnum):
    DIRECT_SELLER = "direct_seller"
    AGGREGATOR = "aggregator"
    EXIT_VENUE = "exit_venue"


class SourceHealth(StrEnum):
    OK = "ok"
    DOWN = "down"
    UNKNOWN = "unknown"


class ScanStatus(StrEnum):
    RUNNING = "running"
    OK = "ok"
    DEGRADED = "degraded"   # at least one source failed -> disturbance, NOT "no deals"
    FAILED = "failed"


class AlertState(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DEAD = "dead"


class EvidenceKind(StrEnum):
    LISTING_SNAPSHOT = "listing_snapshot"
    CHECKOUT_QUOTE = "checkout_quote"
    PURCHASE_RECEIPT = "purchase_receipt"
    EXIT_QUOTE = "exit_quote"
    FEE_SCHEDULE = "fee_schedule"
    PREREQUISITE = "prerequisite"
    MANUAL_NOTE = "manual_note"


class PrereqStatus(StrEnum):
    PROVEN = "proven"
    UNPROVEN = "unproven"
    UNKNOWN = "unknown"
