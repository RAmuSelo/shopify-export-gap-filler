"""Transactions merge tests (spec 7 / 13.2 / 16)."""

from __future__ import annotations

import json

from shopify_gap_filler.orders import build_order_json
from shopify_gap_filler.security import scrub

EXPECTED_TX_KEYS = {
    "id", "kind", "status", "gateway", "formatted_gateway", "amount",
    "currency", "processed_at", "error_code", "payment_id", "account_number",
    "test", "parent_transaction_id",
}


def _first_node(fixture):
    return fixture["data"]["orders"]["edges"][0]["node"]


def test_transactions_nested_under_payment(orders_page1):
    obj = build_order_json(_first_node(orders_page1))
    txs = obj["payment"]["transactions"]
    assert len(txs) == 2
    assert txs[0]["kind"] == "SALE"
    assert txs[0]["status"] == "SUCCESS"
    assert txs[0]["amount"] == "129.90"
    assert txs[0]["currency"] == "EUR"


def test_transaction_keys_match_spec(orders_page1):
    obj = build_order_json(_first_node(orders_page1))
    for tx in obj["payment"]["transactions"]:
        assert set(tx.keys()) == EXPECTED_TX_KEYS


def test_parent_transaction_id_resolved(orders_page1):
    obj = build_order_json(_first_node(orders_page1))
    capture = obj["payment"]["transactions"][1]
    assert capture["kind"] == "CAPTURE"
    assert capture["parent_transaction_id"] == "gid://shopify/OrderTransaction/5001"


def test_account_number_preserved_masked(orders_page1):
    obj = build_order_json(_first_node(orders_page1))
    assert obj["payment"]["transactions"][0]["account_number"] == "•••• 4242"


def test_no_authorization_code_or_payment_details(orders_page1):
    obj = build_order_json(_first_node(orders_page1))
    blob = json.dumps(obj)
    assert "authorizationCode" not in blob
    assert "authorization_code" not in blob
    assert "paymentDetails" not in blob


def test_pci_scrubbed_before_merge(orders_with_pci):
    # Simulate the real pipeline: scrub the raw response, then build JSON.
    cleaned = scrub(orders_with_pci)
    node = cleaned["data"]["orders"]["edges"][0]["node"]
    obj = build_order_json(node)
    blob = json.dumps(obj)
    for token in ["paymentDetails", "creditCard", "cvv", "avs", "bin",
                  "expiration", "wallet", "411111"]:
        assert token not in blob
    # The non-sensitive masked account number still survives.
    assert obj["payment"]["transactions"][0]["account_number"] == "•••• 1111"


def test_gateway_names_in_payment(orders_page1):
    obj = build_order_json(_first_node(orders_page1))
    assert obj["payment"]["gateway_names"] == ["bogus_gateway", "manual"]
    assert obj["payment"]["display_financial_status"] == "PAID"
