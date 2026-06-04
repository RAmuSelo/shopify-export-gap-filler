"""Order flattening tests (spec 13.1 / 16)."""

from __future__ import annotations

from shopify_gap_filler.orders import ORDERS_CSV_COLUMNS, flatten_order_row


def _first_node(fixture):
    return fixture["data"]["orders"]["edges"][0]["node"]


def _second_node(fixture):
    return fixture["data"]["orders"]["edges"][1]["node"]


def test_flatten_produces_all_columns(orders_page1):
    row = flatten_order_row(_first_node(orders_page1))
    assert set(row.keys()) == set(ORDERS_CSV_COLUMNS)


def test_flatten_basic_values(orders_page1):
    row = flatten_order_row(_first_node(orders_page1))
    assert row["order_id"] == "gid://shopify/Order/1001"
    assert row["name"] == "#1001"
    assert row["display_financial_status"] == "PAID"
    assert row["currency_code"] == "EUR"
    assert row["total_price"] == "129.90"
    assert row["subtotal_price"] == "109.90"
    assert row["line_items_count"] == 2


def test_flatten_joins_lists(orders_page1):
    row = flatten_order_row(_first_node(orders_page1))
    assert row["payment_gateway_names"] == "bogus_gateway|manual"
    assert row["tags"] == "vip|repeat"
    assert row["discount_codes"] == "WELCOME10"


def test_flatten_custom_attributes_joined(orders_page1):
    row = flatten_order_row(_first_node(orders_page1))
    assert row["custom_attributes"] == "gift_wrap=yes|delivery_slot=morning"


def test_flatten_protected_fields_present(orders_page1):
    row = flatten_order_row(_first_node(orders_page1))
    assert row["customer_email"] == "buyer@example.com"
    assert row["billing_country"] == "France"
    assert row["customer_id"] == "gid://shopify/Customer/9001"


def test_flatten_nulls_become_empty_without_crashing(orders_page1):
    # Second order has many nulls (no customer, no addresses, empty lists).
    row = flatten_order_row(_second_node(orders_page1))
    assert row["customer_email"] == ""
    assert row["billing_country"] == ""
    assert row["customer_id"] == ""
    assert row["payment_gateway_names"] == ""
    assert row["tags"] == ""
    assert row["total_tax"] == ""  # totalTaxSet was null
    assert row["line_items_count"] == 0
    assert row["cancel_reason"] == "CUSTOMER"
