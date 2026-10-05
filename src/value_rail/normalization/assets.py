"""Asset normalization. Ticker equality never implies identity."""

from __future__ import annotations

from ..domain.identity import AssetIdentity, can_merge_assets

__all__ = ["AssetIdentity", "can_merge_assets", "normalize_contract"]


def normalize_contract(chain: str, address: str) -> AssetIdentity:
    return AssetIdentity(symbol="", chain=(chain or "unknown").strip().lower(),
                         contract_address=(address or "unknown").strip().lower())
