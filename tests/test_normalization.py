from __future__ import annotations

from decimal import Decimal

import pytest

from value_rail.domain.identity import AssetIdentity, can_merge_assets
from value_rail.normalization.price import parse_price_text


# 6
@pytest.mark.parametrize("raw", ["$100", "$ 100", "100$", "100 $"])
def test_case06_dollar_sign_alone_is_not_usd(raw):
    p = parse_price_text(raw)
    assert p.amount == Decimal("100")
    assert p.currency == "unknown"
    assert "ambiguous" in p.note


@pytest.mark.parametrize("raw,amount,cur", [
    ("1,20 €", "1.20", "EUR"), ("56,00 EUR", "56.00", "EUR"), ("€1.234,56", "1234.56", "EUR"),
    ("US$100", "100", "USD"), ("100 USD", "100", "USD"), ("£5", "5", "GBP"), ("12.50", "12.50", "unknown"),
])
def test_price_parsing(raw, amount, cur):
    p = parse_price_text(raw)
    assert p.amount == Decimal(amount) and p.currency == cur


# 7
def test_case07_same_ticker_other_chain_or_contract_never_merges():
    a = AssetIdentity(symbol="USDX", chain="synthetic-chain-a", contract_address="0xAAA")
    b = AssetIdentity(symbol="USDX", chain="synthetic-chain-b", contract_address="0xAAA")
    c = AssetIdentity(symbol="USDX", chain="synthetic-chain-a", contract_address="0xBBB")
    same = AssetIdentity(symbol="usdx-renamed", chain="Synthetic-Chain-A", contract_address="0xaaa")
    assert not can_merge_assets(a, b)
    assert not can_merge_assets(a, c)
    assert can_merge_assets(a, same)  # ticker irrelevant, chain+contract decide
    assert not can_merge_assets(AssetIdentity(symbol="X", chain="unknown", contract_address="0x1"),
                                AssetIdentity(symbol="X", chain="unknown", contract_address="0x1"))
