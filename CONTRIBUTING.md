# Contributing to shopify-export-gap-filler

Thanks for your interest in improving this tool. It's a small, focused CLI, and
contributions that keep it small and focused are very welcome.

## Ground rules

- **Never weaken the PCI posture.** The GraphQL queries must not select
  `paymentDetails` or any card field, and the response denylist in
  `src/shopify_gap_filler/security.py` must stay intact. PRs that add card data
  will be declined.
- **Read-only by design.** The tool only reads from the Shopify Admin API; it
  never writes back to a store.
- **No secrets in the repo.** Use `.env` (git-ignored) locally; never commit a
  token. Tests must not require a real store or token.

## Development setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest -q
```

All tests use synthetic fixtures and a fake HTTP transport — no network, no real
store, no tokens.

## Making a change

1. Open an issue first for anything non-trivial, so we can agree on the approach.
2. Keep PRs small and focused; one logical change per PR.
3. Add or update tests for any behavior change (the suite is offline and fast).
4. Run `python -m pytest -q` and make sure CI (Python 3.11 / 3.12) is green.
5. Match the existing style; no new runtime dependencies without discussion
   (the only runtime dep is `requests`).

## Reporting bugs

Please include: the command you ran (with the token redacted), the Shopify API
version, what you expected, and what happened. Never paste a real token.

## Scope

In scope: filling documented gaps in Shopify's native CSV export via the GraphQL
Admin API, safely. Out of scope: writing to Shopify, scraping, REST execution,
multi-store OAuth, and anything touching card/PCI data.
