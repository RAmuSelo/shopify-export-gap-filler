"""Abandoned checkout flattening tests (spec 13.3 / 13.4 / 16)."""

from __future__ import annotations

from shopify_gap_filler.abandoned import (
    ABANDONED_CSV_COLUMNS,
    build_abandoned_json,
    flatten_abandoned_row,
)


def _node(fixture, index=0):
    return fixture["data"]["abandonedCheckouts"]["edges"][index]["node"]


def test_flatten_produces_all_columns(abandoned_checkouts):
    row = flatten_abandoned_row(_node(abandoned_checkouts))
    assert set(row.keys()) == set(ABANDONED_CSV_COLUMNS)


def test_recovery_url_present(abandoned_checkouts):
    row = flatten_abandoned_row(_node(abandoned_checkouts))
    assert row["abandoned_checkout_url"] == "https://example-store.myshopify.com/recover/abc"


def test_line_items_count(abandoned_checkouts):
    row = flatten_abandoned_row(_node(abandoned_checkouts))
    assert row["line_items_count"] == 2


def test_email_via_customer(abandoned_checkouts):
    row = flatten_abandoned_row(_node(abandoned_checkouts))
    assert row["customer_email"] == "buyer@example.com"
    assert row["customer_id"] == "gid://shopify/Customer/8001"


def test_total_discount_singular_field(abandoned_checkouts):
    row = flatten_abandoned_row(_node(abandoned_checkouts))
    assert row["total_discount"] == "5.00"
    assert row["total_price"] == "75.00"
    assert row["currency_code"] == "EUR"
    assert row["taxes_included"] is True


def test_null_customer_and_addresses(abandoned_checkouts):
    row = flatten_abandoned_row(_node(abandoned_checkouts, index=1))
    assert row["customer_email"] == ""
    assert row["customer_id"] == ""
    assert row["billing_country"] == ""
    assert row["total_tax"] == ""  # totalTaxSet null
    assert row["line_items_count"] == 1


def test_json_structure(abandoned_checkouts):
    obj = build_abandoned_json(_node(abandoned_checkouts))
    assert obj["checkout_id"] == "gid://shopify/AbandonedCheckout/3001"
    assert obj["totals"]["total_discount"] == "5.00"
    assert obj["tax_lines"][0]["title"] == "TVA"
    assert obj["tax_lines"][0]["price"] == "12.50"
    assert obj["customer"]["email"] == "buyer@example.com"
    assert len(obj["line_items"]) == 2
