"""Pagination tests (spec 11 / 16). Zero network — fake transport."""

from __future__ import annotations

from shopify_gap_filler.client import ShopifyGraphQLClient
from shopify_gap_filler.orders import collect_orders, iter_order_pages


def test_pagination_follows_endcursor(fake_config, make_transport, orders_page1, orders_page2):
    transport = make_transport([(200, orders_page1), (200, orders_page2)])
    client = ShopifyGraphQLClient(fake_config, transport=transport)

    pages = list(
        iter_order_pages(client, query_filter=None, page_size=250)
    )
    assert len(pages) == 2
    assert len(pages[0]) == 2  # page1 has 2 orders
    assert len(pages[1]) == 1  # page2 has 1 order

    # The 2nd request must carry after = endCursor of page 1.
    second_vars = transport.calls[1]["body"]["variables"]
    assert second_vars["after"] == "CURSOR_PAGE_1_END"
    # The 1st request starts with after = None.
    assert transport.calls[0]["body"]["variables"]["after"] is None


def test_pagination_stops_on_has_next_false(fake_config, make_transport, orders_page2):
    # A single page with hasNextPage=false must not request a second page.
    transport = make_transport([(200, orders_page2)])
    client = ShopifyGraphQLClient(fake_config, transport=transport)
    pages = list(iter_order_pages(client, query_filter=None, page_size=250))
    assert len(pages) == 1
    assert len(transport.calls) == 1


def test_collect_orders_aggregates_all_pages(fake_config, make_transport, orders_page1, orders_page2):
    transport = make_transport([(200, orders_page1), (200, orders_page2)])
    client = ShopifyGraphQLClient(fake_config, transport=transport)
    csv_rows, json_objects = collect_orders(client, query_filter=None, page_size=250)
    assert len(csv_rows) == 3
    assert len(json_objects) == 3
    ids = [r["order_id"] for r in csv_rows]
    assert ids == [
        "gid://shopify/Order/1001",
        "gid://shopify/Order/1002",
        "gid://shopify/Order/1003",
    ]


def test_query_filter_passed_through(fake_config, make_transport, orders_page2):
    transport = make_transport([(200, orders_page2)])
    client = ShopifyGraphQLClient(fake_config, transport=transport)
    list(iter_order_pages(client, query_filter="created_at:>=2025-01-01", page_size=100))
    sent = transport.calls[0]["body"]["variables"]
    assert sent["query"] == "created_at:>=2025-01-01"
    assert sent["first"] == 100
