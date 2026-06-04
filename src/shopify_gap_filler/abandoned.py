"""Abandoned checkouts export: paginate, scrub, flatten.

LOCKED spec sections 8, 10.2, 11, 13.3, 13.4.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from .client import ShopifyGraphQLClient
from .orders import _edges_nodes, _join, _money, _money_currency
from .queries import ABANDONED_CHECKOUTS_QUERY
from .security import scrub

logger = logging.getLogger("shopify_gap_filler.abandoned")

# CSV column order (LOCKED spec 13.3).
ABANDONED_CSV_COLUMNS = [
    "checkout_id",
    "abandoned_checkout_url",
    "created_at",
    "updated_at",
    "completed_at",
    "currency_code",
    "total_price",
    "subtotal_price",
    "total_tax",
    "total_discount",
    "taxes_included",
    "note",
    "discount_codes",
    "line_items_count",
    "customer_id",
    "customer_email",
    "billing_country",
    "shipping_country",
]


def iter_abandoned_pages(
    client: ShopifyGraphQLClient,
    *,
    query_filter: str | None,
    page_size: int,
) -> Iterator[list[dict]]:
    """Yield successive pages of abandoned-checkout nodes (PCI-scrubbed)."""
    after: str | None = None
    page_index = 0
    while True:
        variables: dict[str, Any] = {"first": page_size, "after": after}
        if query_filter:
            variables["query"] = query_filter
        data = client.execute(ABANDONED_CHECKOUTS_QUERY, variables)
        data = scrub(data)
        connection = (data or {}).get("abandonedCheckouts") or {}
        nodes = _edges_nodes(connection)
        page_index += 1
        logger.info("abandoned-checkouts page %d: %d node(s)", page_index, len(nodes))
        yield nodes
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
        if not after:
            break


def _currency_from_totals(node: dict) -> str:
    """Pick a currency code from one of the money bags present."""
    for key in ("totalPriceSet", "subtotalPriceSet", "totalDiscountSet", "totalTaxSet"):
        cur = _money_currency(node.get(key))
        if cur:
            return cur
    return ""


def flatten_abandoned_row(node: dict) -> dict[str, Any]:
    """Flatten one abandoned-checkout node into the CSV row schema (13.3)."""
    line_items = _edges_nodes(node.get("lineItems"))
    customer = node.get("customer") or {}
    billing = node.get("billingAddress") or {}
    shipping = node.get("shippingAddress") or {}
    return {
        "checkout_id": node.get("id", ""),
        "abandoned_checkout_url": node.get("abandonedCheckoutUrl") or "",
        "created_at": node.get("createdAt", ""),
        "updated_at": node.get("updatedAt", ""),
        "completed_at": node.get("completedAt") or "",
        "currency_code": _currency_from_totals(node),
        "total_price": _money(node.get("totalPriceSet")),
        "subtotal_price": _money(node.get("subtotalPriceSet")),
        "total_tax": _money(node.get("totalTaxSet")),
        "total_discount": _money(node.get("totalDiscountSet")),
        "taxes_included": node.get("taxesIncluded"),
        "note": node.get("note") or "",
        "discount_codes": _join(node.get("discountCodes")),
        "line_items_count": len(line_items),
        "customer_id": customer.get("id") or "",
        "customer_email": customer.get("email") or "",
        "billing_country": billing.get("country") or "",
        "shipping_country": shipping.get("country") or "",
    }


def build_abandoned_json(node: dict) -> dict[str, Any]:
    """Build the rich nested JSON object for one abandoned checkout (13.4)."""
    line_items = [
        {"title": li.get("title"), "quantity": li.get("quantity")}
        for li in _edges_nodes(node.get("lineItems"))
    ]
    tax_lines = [
        {
            "title": tl.get("title"),
            "price": _money(tl.get("priceSet")),
            "currency": _money_currency(tl.get("priceSet")),
        }
        for tl in (node.get("taxLines") or [])
        if isinstance(tl, dict)
    ]
    customer = node.get("customer") or {}
    billing = node.get("billingAddress") or {}
    shipping = node.get("shippingAddress") or {}
    return {
        "checkout_id": node.get("id"),
        "abandoned_checkout_url": node.get("abandonedCheckoutUrl"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "completed_at": node.get("completedAt"),
        "totals": {
            "total_price": _money(node.get("totalPriceSet")),
            "subtotal_price": _money(node.get("subtotalPriceSet")),
            "total_tax": _money(node.get("totalTaxSet")),
            "total_discount": _money(node.get("totalDiscountSet")),
        },
        "taxes_included": node.get("taxesIncluded"),
        "note": node.get("note"),
        "discount_codes": node.get("discountCodes") or [],
        "tax_lines": tax_lines,
        "line_items": line_items,
        "customer": {"id": customer.get("id"), "email": customer.get("email")},
        "addresses": {
            "billing": {"country": billing.get("country"), "city": billing.get("city")},
            "shipping": {"country": shipping.get("country"), "city": shipping.get("city")},
        },
    }


def collect_abandoned(
    client: ShopifyGraphQLClient,
    *,
    query_filter: str | None,
    page_size: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect all abandoned checkouts. Returns ``(csv_rows, json_objects)``."""
    csv_rows: list[dict[str, Any]] = []
    json_objects: list[dict[str, Any]] = []
    for page in iter_abandoned_pages(client, query_filter=query_filter, page_size=page_size):
        for node in page:
            csv_rows.append(flatten_abandoned_row(node))
            json_objects.append(build_abandoned_json(node))
    return csv_rows, json_objects
