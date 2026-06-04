"""GraphQL Admin API query documents.

These are exact query strings derived from the LOCKED spec (sections 10.1 and
10.2). They contain no logic. No deprecated fields are selected. No subfield of
the ``paymentDetails`` union is ever requested (PCI exclusion).

Sources (official Shopify docs):
- orders query: https://shopify.dev/docs/api/admin-graphql/latest/queries/orders
- Order object: https://shopify.dev/docs/api/admin-graphql/latest/objects/Order
- OrderTransaction: https://shopify.dev/docs/api/admin-graphql/latest/objects/OrderTransaction
- abandonedCheckouts query: https://shopify.dev/docs/api/admin-graphql/latest/queries/abandonedCheckouts
- AbandonedCheckout object: https://shopify.dev/docs/api/admin-graphql/latest/objects/AbandonedCheckout
"""

# The transactions sub-selection is split out so the orders query can be built
# with or without it (CLI flag --no-transactions). It contains ONLY
# non-sensitive metadata. There is intentionally no paymentDetails selection.
_ORDER_TRANSACTIONS_BLOCK = """
        transactions {
          id
          kind
          status
          gateway
          formattedGateway
          processedAt
          errorCode
          paymentId
          accountNumber
          test
          amountSet { shopMoney { amount currencyCode } }
          parentTransaction { id }
        }"""


def build_orders_query(include_transactions: bool = True) -> str:
    """Return the orders GraphQL document.

    When ``include_transactions`` is False the (already non-sensitive)
    transactions block is omitted to lower the GraphQL query cost.
    """
    transactions = _ORDER_TRANSACTIONS_BLOCK if include_transactions else ""
    return _ORDERS_QUERY_TEMPLATE.format(transactions=transactions)


_ORDERS_QUERY_TEMPLATE = """\
query GapFillerOrders($first: Int!, $after: String, $query: String) {{
  orders(first: $first, after: $after, query: $query, sortKey: PROCESSED_AT) {{
    pageInfo {{
      hasNextPage
      endCursor
    }}
    edges {{
      cursor
      node {{
        id
        name
        createdAt
        processedAt
        cancelledAt
        cancelReason
        displayFinancialStatus
        displayFulfillmentStatus
        paymentGatewayNames
        sourceName
        tags
        note
        confirmationNumber
        clientIp
        currencyCode
        customAttributes {{
          key
          value
        }}
        totalPriceSet      {{ shopMoney {{ amount currencyCode }} }}
        subtotalPriceSet   {{ shopMoney {{ amount currencyCode }} }}
        totalTaxSet        {{ shopMoney {{ amount currencyCode }} }}
        totalDiscountsSet  {{ shopMoney {{ amount currencyCode }} }}
        discountCodes
        lineItems(first: 50) {{
          edges {{
            node {{
              title
              quantity
              originalUnitPriceSet {{ shopMoney {{ amount currencyCode }} }}
            }}
          }}
        }}{transactions}
        customer {{ id }}
        email
        billingAddress  {{ country city }}
        shippingAddress {{ country city }}
      }}
    }}
  }}
}}
"""

# Convenience constant: the full orders query WITH transactions.
ORDERS_QUERY = build_orders_query(include_transactions=True)


ABANDONED_CHECKOUTS_QUERY = """\
query GapFillerAbandonedCheckouts($first: Int!, $after: String, $query: String) {
  abandonedCheckouts(first: $first, after: $after, query: $query, sortKey: CREATED_AT) {
    pageInfo {
      hasNextPage
      endCursor
    }
    edges {
      cursor
      node {
        id
        abandonedCheckoutUrl
        createdAt
        updatedAt
        completedAt
        taxesIncluded
        note
        discountCodes
        totalPriceSet     { shopMoney { amount currencyCode } }
        subtotalPriceSet  { shopMoney { amount currencyCode } }
        totalTaxSet       { shopMoney { amount currencyCode } }
        totalDiscountSet  { shopMoney { amount currencyCode } }
        taxLines {
          title
          priceSet { shopMoney { amount currencyCode } }
        }
        lineItems(first: 50) {
          edges {
            node {
              title
              quantity
            }
          }
        }
        customer { id email }
        billingAddress  { country city }
        shippingAddress { country city }
      }
    }
  }
}
"""
