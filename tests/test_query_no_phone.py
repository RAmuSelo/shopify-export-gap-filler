"""Data-minimization & PCI guards on the active GraphQL queries. No network."""

from __future__ import annotations

from shopify_gap_filler.queries import build_orders_query, ABANDONED_CHECKOUTS_QUERY


def test_orders_query_does_not_request_phone():
    # `phone` is protected customer data not used in any output -> never requested.
    q = build_orders_query(include_transactions=True)
    assert "phone" not in q
    q_no_tx = build_orders_query(include_transactions=False)
    assert "phone" not in q_no_tx


def test_orders_query_excludes_payment_details():
    q = build_orders_query(include_transactions=True)
    assert "paymentDetails" not in q
    assert "creditCard" not in q


def test_orders_query_keeps_used_customer_fields():
    # email + addresses ARE used in the output and stay (protected-data degradation handled at runtime).
    q = build_orders_query(include_transactions=True)
    for field in ("email", "billingAddress", "shippingAddress"):
        assert field in q


def test_abandoned_query_excludes_payment_details_and_phone():
    assert "paymentDetails" not in ABANDONED_CHECKOUTS_QUERY
    assert "phone" not in ABANDONED_CHECKOUTS_QUERY
