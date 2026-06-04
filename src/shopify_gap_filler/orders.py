"""Orders export: paginate, scrub, merge transactions, flatten.

LOCKED spec sections 6, 7, 10.1, 11, 13.1, 13.2.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from .client import ShopifyGraphQLClient
from .queries import build_orders_query
from .security import scrub

logger = logging.getLogger("shopify_gap_filler.orders")

# CSV column order (LOCKED spec 13.1).
ORDERS_CSV_COLUMNS = [
    "order_id",
    "name",
    "created_at",
    "processed_at",
    "display_financial_status",
    "display_fulfillment_status",
    "currency_code",
    "total_price",
    "subtotal_price",
    "total_tax",
    "total_discounts",
    "payment_gateway_names",
    "source_name",
    "tags",
    "note",
    "custom_attributes",
    "cancel_reason",
    "cancelled_at",
    "confirmation_number",
    "client_ip",
    "customer_id",
    "customer_email",
    "billing_country",
    "shipping_country",
    "discount_codes",
    "line_items_count",
]


def _money(node: Any) -> str:
    """Extract shopMoney.amount as a raw string ("" if absent)."""
    if not isinstance(node, dict):
        return ""
    shop_money = node.get("shopMoney") or {}
    amount = shop_money.get("amount")
    return "" if amount is None else str(amount)


def _money_currency(node: Any) -> str:
    if not isinstance(node, dict):
        return ""
    shop_money = node.get("shopMoney") or {}
    return shop_money.get("currencyCode") or ""


def _join(values: Any, sep: str = "|") -> str:
    if not isinstance(values, list):
        return ""
    return sep.join("" if v is None else str(v) for v in values)


def _edges_nodes(connection: Any) -> list[dict]:
    if not isinstance(connection, dict):
        return []
    edges = connection.get("edges") or []
    nodes = []
    for edge in edges:
        if isinstance(edge, dict) and isinstance(edge.get("node"), dict):
            nodes.append(edge["node"])
    return nodes


def iter_order_pages(
    client: ShopifyGraphQLClient,
    *,
    query_filter: str | None,
    page_size: int,
    include_transactions: bool = True,
) -> Iterator[list[dict]]:
    """Yield successive pages of order nodes (already PCI-scrubbed).

    Follows the Relay cursor: passes ``first`` + ``after`` and stops when
    ``pageInfo.hasNextPage`` is False (LOCKED spec 11).
    """
    document = build_orders_query(include_transactions=include_transactions)
    after: str | None = None
    page_index = 0
    while True:
        variables: dict[str, Any] = {"first": page_size, "after": after}
        if query_filter:
            variables["query"] = query_filter
        data = client.execute(document, variables)
        data = scrub(data)  # defense in depth before anything leaves this layer
        connection = (data or {}).get("orders") or {}
        nodes = _edges_nodes(connection)
        page_index += 1
        logger.info("orders page %d: %d node(s)", page_index, len(nodes))
        yield nodes
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        after = page_info.get("endCursor")
        if not after:
            break


def flatten_order_row(node: dict) -> dict[str, Any]:
    """Flatten one order node into the flat CSV row schema (spec 13.1)."""
    line_items = _edges_nodes(node.get("lineItems"))
    customer = node.get("customer") or {}
    billing = node.get("billingAddress") or {}
    shipping = node.get("shippingAddress") or {}
    custom_attributes = node.get("customAttributes") or []
    attrs_joined = "|".join(
        f"{a.get('key', '')}={a.get('value', '')}"
        for a in custom_attributes
        if isinstance(a, dict)
    )
    return {
        "order_id": node.get("id", ""),
        "name": node.get("name", ""),
        "created_at": node.get("createdAt", ""),
        "processed_at": node.get("processedAt", ""),
        "display_financial_status": node.get("displayFinancialStatus", ""),
        "display_fulfillment_status": node.get("displayFulfillmentStatus", ""),
        "currency_code": node.get("currencyCode", ""),
        "total_price": _money(node.get("totalPriceSet")),
        "subtotal_price": _money(node.get("subtotalPriceSet")),
        "total_tax": _money(node.get("totalTaxSet")),
        "total_discounts": _money(node.get("totalDiscountsSet")),
        "payment_gateway_names": _join(node.get("paymentGatewayNames")),
        "source_name": node.get("sourceName") or "",
        "tags": _join(node.get("tags")),
        "note": node.get("note") or "",
        "custom_attributes": attrs_joined,
        "cancel_reason": node.get("cancelReason") or "",
        "cancelled_at": node.get("cancelledAt") or "",
        "confirmation_number": node.get("confirmationNumber") or "",
        "client_ip": node.get("clientIp") or "",
        "customer_id": customer.get("id") or "",
        "customer_email": node.get("email") or "",
        "billing_country": billing.get("country") or "",
        "shipping_country": shipping.get("country") or "",
        "discount_codes": _join(node.get("discountCodes")),
        "line_items_count": len(line_items),
    }


def build_order_json(node: dict) -> dict[str, Any]:
    """Build the rich nested JSON object for one order (spec 13.2).

    The ``transactions`` sub-array carries only non-sensitive metadata. No card
    fields are present (queries never request them; scrub removes any stray).
    """
    line_items = [
        {
            "title": li.get("title"),
            "quantity": li.get("quantity"),
            "unit_price": _money(li.get("originalUnitPriceSet")),
            "currency": _money_currency(li.get("originalUnitPriceSet")),
        }
        for li in _edges_nodes(node.get("lineItems"))
    ]
    transactions = []
    for tx in node.get("transactions") or []:
        if not isinstance(tx, dict):
            continue
        parent = tx.get("parentTransaction") or {}
        transactions.append(
            {
                "id": tx.get("id"),
                "kind": tx.get("kind"),
                "status": tx.get("status"),
                "gateway": tx.get("gateway"),
                "formatted_gateway": tx.get("formattedGateway"),
                "amount": _money(tx.get("amountSet")),
                "currency": _money_currency(tx.get("amountSet")),
                "processed_at": tx.get("processedAt"),
                "error_code": tx.get("errorCode"),
                "payment_id": tx.get("paymentId"),
                "account_number": tx.get("accountNumber"),  # masked by API
                "test": tx.get("test"),
                "parent_transaction_id": parent.get("id"),
            }
        )
    customer = node.get("customer") or {}
    billing = node.get("billingAddress") or {}
    shipping = node.get("shippingAddress") or {}
    return {
        "order_id": node.get("id"),
        "name": node.get("name"),
        "created_at": node.get("createdAt"),
        "processed_at": node.get("processedAt"),
        "display_financial_status": node.get("displayFinancialStatus"),
        "display_fulfillment_status": node.get("displayFulfillmentStatus"),
        "currency_code": node.get("currencyCode"),
        "totals": {
            "total_price": _money(node.get("totalPriceSet")),
            "subtotal_price": _money(node.get("subtotalPriceSet")),
            "total_tax": _money(node.get("totalTaxSet")),
            "total_discounts": _money(node.get("totalDiscountsSet")),
        },
        "source_name": node.get("sourceName"),
        "tags": node.get("tags") or [],
        "note": node.get("note"),
        "custom_attributes": [
            {"key": a.get("key"), "value": a.get("value")}
            for a in (node.get("customAttributes") or [])
            if isinstance(a, dict)
        ],
        "cancel_reason": node.get("cancelReason"),
        "cancelled_at": node.get("cancelledAt"),
        "confirmation_number": node.get("confirmationNumber"),
        "client_ip": node.get("clientIp"),
        "customer": {"id": customer.get("id"), "email": node.get("email")},
        "addresses": {
            "billing": {"country": billing.get("country"), "city": billing.get("city")},
            "shipping": {"country": shipping.get("country"), "city": shipping.get("city")},
        },
        "discount_codes": node.get("discountCodes") or [],
        "line_items": line_items,
        "payment": {
            "gateway_names": node.get("paymentGatewayNames") or [],
            "display_financial_status": node.get("displayFinancialStatus"),
            "transactions": transactions,
        },
    }


def collect_orders(
    client: ShopifyGraphQLClient,
    *,
    query_filter: str | None,
    page_size: int,
    include_transactions: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Collect all orders across pages.

    Returns ``(csv_rows, json_objects)``.
    """
    csv_rows: list[dict[str, Any]] = []
    json_objects: list[dict[str, Any]] = []
    for page in iter_order_pages(
        client,
        query_filter=query_filter,
        page_size=page_size,
        include_transactions=include_transactions,
    ):
        for node in page:
            csv_rows.append(flatten_order_row(node))
            json_objects.append(build_order_json(node))
    return csv_rows, json_objects
