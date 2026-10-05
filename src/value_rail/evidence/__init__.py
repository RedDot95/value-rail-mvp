"""Evidence: hashing, drafting and lookup of evidence records.

Evidence is append-only. Each record references a subject (e.g. "offer_snapshot:12", "quote:4")
and carries a content hash of its payload so later tampering/corrections are detectable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from ..domain.enums import EvidenceKind


def content_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(blob).hexdigest()


class EvidenceDraft(BaseModel):
    kind: EvidenceKind
    source_key: str
    captured_at: datetime
    scope: str = "unknown"
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    is_synthetic: bool = False
