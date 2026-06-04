# shopify-export-gap-filler

[![Tests](https://github.com/RAmuSelo/shopify-export-gap-filler/actions/workflows/tests.yml/badge.svg)](https://github.com/RAmuSelo/shopify-export-gap-filler/actions/workflows/tests.yml)

Enrich your Shopify exports with what the native CSV does not include: rich
order details, **non-sensitive** payment metadata, and abandoned checkouts.

GraphQL Admin API only. **Read-only.** **No card / PCI data, ever.**

---

## Security & PCI warning (read first)

This tool **never** requests, writes, or logs card data. The GraphQL queries do
not select the `paymentDetails` union or any card field, and a defensive
denylist scrubs every API response before anything is written to disk.

Explicitly excluded (denylist, see `src/shopify_gap_filler/security.py`):

- `OrderTransaction.paymentDetails` (the entire union)
- `CardPaymentDetails.*` (masked number, BIN, company, name, wallet, expiration)
- `avsResultCode`, `cvvResultCode`

Kept on purpose: `OrderTransaction.accountNumber`, which Shopify already returns
**masked** and is not card data.

The tool uses read-only scopes only and never writes anything back to Shopify.

---

## Why this tool

Shopify's native CSV export omits many fields that are available through the
GraphQL Admin API:

| Native CSV export | GraphQL Admin API (this tool) |
|---|---|
| Limited order fields | `displayFinancialStatus`, `customAttributes`, `confirmationNumber`, `clientIp`, money bags, … |
| No payment metadata | Non-sensitive `OrderTransaction` fields (gateway, kind, status, amount, …) |
| No abandoned checkouts | `abandonedCheckouts` with the recovery URL |

---

## Requirements

- A Shopify store and a **custom app** with an Admin API access token.
- Scope **`read_orders`** — the only required scope. It covers `Order`,
  `OrderTransaction`, **and** `AbandonedCheckout`.
- Optional scope **`read_all_orders`** (Shopify approval required) if `--since`
  goes back more than 60 days; otherwise the API limits to the last 60 days and
  the tool warns and continues.
- Optional scope **`read_customers`** plus **protected customer data** approval
  if you want customer email / name / address. Without approval those fields
  come back `null`; the tool leaves the columns blank and continues.
- Python 3.9+.

Note: there is **no** Admin scope named `read_checkouts`; `read_orders` already
covers abandoned checkouts.

---

## Installation

```bash
git clone <your-fork-url> shopify-export-gap-filler
cd shopify-export-gap-filler
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

The only runtime dependency is `requests`. Tests need no installation and no
network (they inject a fake transport).

---

## Configuration

```bash
cp .env.example .env
# edit .env and set SHOPIFY_SHOP and SHOPIFY_ADMIN_API_TOKEN
```

Never commit `.env` (it is in `.gitignore`).

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SHOPIFY_SHOP` | yes | — | `my-store` or `my-store.myshopify.com` |
| `SHOPIFY_ADMIN_API_TOKEN` | yes | — | Custom app token (`shpat_…`). Never logged. |
| `SHOPIFY_API_VERSION` | no | `2026-04` | Format `YYYY-MM`. Override with care. |
| `SHOPIFY_MAX_RETRIES` | no | `5` | Backoff cap on 429 / 5xx / THROTTLED. |
| `SHOPIFY_TIMEOUT_SECONDS` | no | `30` | Per-request HTTP timeout. |

### Getting a token

In your Shopify admin: **Settings → Apps and sales channels → Develop apps →
Create an app → Configure Admin API scopes** (enable `read_orders`) → **Install
app** → copy the **Admin API access token**. See the official docs:
<https://shopify.dev/docs/apps/build/authentication-authorization>.

---

## Usage

```bash
# Orders (with non-sensitive transactions) since a date, to CSV
shopify-gap-filler orders --since 2025-01-01 --out orders.csv

# Orders for a date range, both CSV and JSON (base path; extensions added)
shopify-gap-filler orders --since 2025-01-01 --until 2025-12-31 --format both --out exports/orders_2025

# Lighter query without the transactions block
shopify-gap-filler orders --since 2025-01-01 --no-transactions

# Abandoned checkouts to JSON
shopify-gap-filler abandoned-checkouts --since 2025-06-01 --format json --out abandoned.json

# See exactly what would be sent, with NO network call
shopify-gap-filler orders --since 2025-01-01 --dry-run
```

Common options: `--format {csv,json,both}`, `--out`, `--since`, `--until`,
`--limit` (1..250 page size), `--api-version`, `--delimiter`, `--dry-run`,
`--quiet` / `--verbose`.

There is no standalone `transactions` subcommand: transactions are a
sub-selection of `orders`.

---

## Output schema

### `orders` — CSV columns

```
order_id, name, created_at, processed_at, display_financial_status,
display_fulfillment_status, currency_code, total_price, subtotal_price,
total_tax, total_discounts, payment_gateway_names, source_name, tags, note,
custom_attributes, cancel_reason, cancelled_at, confirmation_number, client_ip,
customer_id, customer_email, billing_country, shipping_country,
discount_codes, line_items_count
```

List fields (`payment_gateway_names`, `discount_codes`) are joined with `|`;
`custom_attributes` are `key=value` joined with `|`. The JSON output nests a
`payment` object with the non-sensitive `transactions` array. See
`examples/sample_orders.csv` and `examples/sample_orders.json`.

### `abandoned-checkouts` — CSV columns

```
checkout_id, abandoned_checkout_url, created_at, updated_at, completed_at,
currency_code, total_price, subtotal_price, total_tax, total_discount,
taxes_included, note, discount_codes, line_items_count,
customer_id, customer_email, billing_country, shipping_country
```

Conventions: UTF-8; default CSV delimiter `,` (`--delimiter ';'` for Excel FR);
ISO 8601 dates as returned by the API (no reformatting); raw `shopMoney.amount`
(no currency conversion); header row always present.

---

## Scopes & data limits

- Without `read_all_orders`, the orders query is limited to the last 60 days;
  the tool warns when `--since` is older and continues on the available window.
- `customer`, `email`, `billingAddress`, `shippingAddress` are
  **protected customer data**. Without approval they return `null`; the tool
  keeps going and leaves the columns blank. **`phone` is intentionally not
  requested** (data minimization — it is not used in any output).

---

## Rate limit & pagination (GraphQL)

The Admin GraphQL API uses a leaky-bucket cost model (points). The client reads
`extensions.cost.throttleStatus`, backs off on HTTP 429 / 5xx and GraphQL
`THROTTLED` (bounded by `SHOPIFY_MAX_RETRIES`, with jitter), and never retries
other 4xx. Pagination follows the Relay cursor: it passes `first` + `after` and
stops when `pageInfo.hasNextPage` is `false`. Requests are sequential (one in
flight) in this version.

---

## Out of scope (this version)

- No browser automation / scraping.
- No writes to Shopify.
- No REST execution path (REST is legacy as of 2024-10-01; kept as
  documentation reference only).
- No public-app OAuth / multi-store (custom-app token only).
- No subscriptions / selling plans.
- No cron / daemon / automation — run on demand.

---

## Tests

```bash
python3 -m pytest -q
```

All tests use synthetic fixtures and a fake HTTP transport: **zero network
calls**, no real store, no real tokens.

---

## API versions

The default is `2026-04` (latest stable). `2026-07` is the release candidate
(not recommended for production). Change the version via `SHOPIFY_API_VERSION`
or `--api-version`. Versioning reference:
<https://shopify.dev/docs/api/usage/versioning>.

---

## Contributing

Issues and pull requests are welcome. Please keep the PCI denylist intact and
never add card fields to the queries.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 The shopify-export-gap-filler
authors.

---

## Sources (official Shopify docs)

- Versioning: <https://shopify.dev/docs/api/usage/versioning>
- REST is legacy: <https://shopify.dev/docs/api/admin-rest/usage/versioning>
- Access scopes: <https://shopify.dev/docs/api/usage/access-scopes>
- Protected customer data: <https://shopify.dev/docs/apps/launch/protected-customer-data>
- `orders` query: <https://shopify.dev/docs/api/admin-graphql/latest/queries/orders>
- `Order` object: <https://shopify.dev/docs/api/admin-graphql/latest/objects/Order>
- `OrderTransaction`: <https://shopify.dev/docs/api/admin-graphql/latest/objects/OrderTransaction>
- `abandonedCheckouts` query: <https://shopify.dev/docs/api/admin-graphql/latest/queries/abandonedCheckouts>
- `AbandonedCheckout` object: <https://shopify.dev/docs/api/admin-graphql/latest/objects/AbandonedCheckout>
- Pagination: <https://shopify.dev/docs/api/usage/pagination-graphql>
- API limits: <https://shopify.dev/docs/api/usage/limits>
