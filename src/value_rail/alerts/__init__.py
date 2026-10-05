"""Alerts: dedup/material-change policy, transactional outbox, pluggable sinks, dispatcher.

Delivery semantics: AT-LEAST-ONCE. A crash after the sink accepted an alert but before the
outbox row was marked `sent` will re-send it on the next dispatch. Every payload carries a stable
`event_id`, so consumers can de-duplicate.
"""
