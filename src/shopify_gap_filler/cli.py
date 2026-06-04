"""Command-line interface (LOCKED spec section 15).

Subcommands: ``orders`` and ``abandoned-checkouts``. Common options:
--format, --out, --since, --until, --limit, --api-version, --dry-run,
--quiet/--verbose, --delimiter. The ``orders`` subcommand adds --no-transactions.

``--dry-run`` performs NO network call: it prints the GraphQL document and the
variables that would be sent, then exits.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Sequence

from . import __version__
from .abandoned import ABANDONED_CSV_COLUMNS, collect_abandoned
from .client import ShopifyGraphQLClient
from .config import ConfigError, DEFAULT_API_VERSION, load_config
from .orders import ORDERS_CSV_COLUMNS, collect_orders
from .output import write_output
from .queries import ABANDONED_CHECKOUTS_QUERY, build_orders_query

logger = logging.getLogger("shopify_gap_filler")

# Shopify Admin "default window" without read_all_orders (spec 5).
_ORDERS_WINDOW_DAYS = 60


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shopify-gap-filler",
        description=(
            "Enrich Shopify exports with data the native CSV omits "
            "(rich order fields, non-sensitive payment metadata, abandoned "
            "checkouts). GraphQL Admin API only. Read-only. No card/PCI data."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    orders = subparsers.add_parser("orders", help="Export orders (+ transactions).")
    _add_common_args(orders)
    orders.add_argument(
        "--no-transactions",
        action="store_true",
        help="Omit the transactions sub-selection (lighter GraphQL query).",
    )
    orders.set_defaults(func=_run_orders)

    abandoned = subparsers.add_parser(
        "abandoned-checkouts", help="Export abandoned checkouts."
    )
    _add_common_args(abandoned)
    abandoned.set_defaults(func=_run_abandoned)

    return parser


def _add_common_args(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--format",
        choices=["csv", "json", "both"],
        default="csv",
        help="Output format (default: csv).",
    )
    p.add_argument(
        "--out",
        default=None,
        help="Output path. For 'both', the base path (extensions added).",
    )
    p.add_argument("--since", default=None, help="Start date YYYY-MM-DD (created_at:>=).")
    p.add_argument("--until", default=None, help="End date YYYY-MM-DD (created_at:<=).")
    p.add_argument(
        "--limit",
        type=int,
        default=250,
        help="GraphQL page size 'first' (1..250, default 250).",
    )
    p.add_argument(
        "--api-version",
        default=None,
        help=f"Override SHOPIFY_API_VERSION (default {DEFAULT_API_VERSION}).",
    )
    p.add_argument("--delimiter", default=",", help="CSV delimiter (default ',').")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not call the network; print the query and variables and exit.",
    )
    verbosity = p.add_mutually_exclusive_group()
    verbosity.add_argument("--quiet", action="store_true", help="Errors only.")
    verbosity.add_argument("--verbose", action="store_true", help="Debug logging.")
    p.add_argument("--env-file", default=".env", help="Path to .env (default ./.env).")


def _configure_logging(args: argparse.Namespace) -> None:
    level = logging.INFO
    if getattr(args, "quiet", False):
        level = logging.ERROR
    elif getattr(args, "verbose", False):
        level = logging.DEBUG
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def build_date_filter(since: str | None, until: str | None) -> str | None:
    """Build a Shopify search-syntax date filter string, or None."""
    parts = []
    if since:
        parts.append(f"created_at:>={since}")
    if until:
        parts.append(f"created_at:<={until}")
    return " ".join(parts) if parts else None


def _validate_limit(limit: int) -> int:
    if limit < 1 or limit > 250:
        raise SystemExit(f"--limit must be between 1 and 250 (got {limit}).")
    return limit


def _warn_if_window_exceeded(since: str | None) -> None:
    """Warn that read_all_orders is needed if --since is older than 60 days."""
    if not since:
        return
    try:
        from datetime import date, datetime

        start = datetime.strptime(since, "%Y-%m-%d").date()
    except ValueError:
        return
    age_days = (date.today() - start).days
    if age_days > _ORDERS_WINDOW_DAYS:
        logger.warning(
            "--since (%s) is older than %d days. Without the 'read_all_orders' "
            "scope (Shopify approval required) the API only returns orders from "
            "the last %d days. Continuing on the available window. See "
            "https://shopify.dev/docs/api/usage/access-scopes",
            since,
            _ORDERS_WINDOW_DAYS,
            _ORDERS_WINDOW_DAYS,
        )


def _default_out(command: str, fmt: str) -> str:
    ext = "json" if fmt == "json" else "csv"
    base = "orders" if command == "orders" else "abandoned_checkouts"
    return f"{base}.{ext}"


def _print_dry_run(document: str, variables: dict) -> None:
    print("DRY RUN — no network call performed.")
    print("=== GraphQL document ===")
    print(document)
    print("=== Variables (first page) ===")
    for key, value in variables.items():
        print(f"  {key} = {value!r}")


def _run_orders(args: argparse.Namespace) -> int:
    limit = _validate_limit(args.limit)
    date_filter = build_date_filter(args.since, args.until)
    include_tx = not args.no_transactions

    # Validate config (incl. credentials) for BOTH dry-run and real run.
    config = load_config(args.env_file, api_version_override=args.api_version)

    if args.dry_run:
        document = build_orders_query(include_transactions=include_tx)
        variables = {"first": limit, "after": None}
        if date_filter:
            variables["query"] = date_filter
        print(
            f"Config validée — boutique {config.shop}, API {config.api_version}. "
            "Aucun appel réseau (dry-run)."
        )
        _print_dry_run(document, variables)
        return 0

    _warn_if_window_exceeded(args.since)
    logger.info("Shop: %s | API %s | token %s", config.shop, config.api_version, config.masked_token())
    client = ShopifyGraphQLClient(config)
    csv_rows, json_objects = collect_orders(
        client, query_filter=date_filter, page_size=limit, include_transactions=include_tx
    )
    out_path = args.out or _default_out("orders", args.format)
    written = write_output(
        csv_rows, json_objects, ORDERS_CSV_COLUMNS,
        fmt=args.format, out_path=out_path, delimiter=args.delimiter,
    )
    logger.info("orders: %d record(s) -> %s", len(csv_rows), ", ".join(str(p) for p in written))
    return 0


def _run_abandoned(args: argparse.Namespace) -> int:
    limit = _validate_limit(args.limit)
    date_filter = build_date_filter(args.since, args.until)

    # Validate config (incl. credentials) for BOTH dry-run and real run.
    config = load_config(args.env_file, api_version_override=args.api_version)

    if args.dry_run:
        variables = {"first": limit, "after": None}
        if date_filter:
            variables["query"] = date_filter
        print(
            f"Config validée — boutique {config.shop}, API {config.api_version}. "
            "Aucun appel réseau (dry-run)."
        )
        _print_dry_run(ABANDONED_CHECKOUTS_QUERY, variables)
        return 0

    logger.info("Shop: %s | API %s | token %s", config.shop, config.api_version, config.masked_token())
    client = ShopifyGraphQLClient(config)
    csv_rows, json_objects = collect_abandoned(
        client, query_filter=date_filter, page_size=limit
    )
    out_path = args.out or _default_out("abandoned-checkouts", args.format)
    written = write_output(
        csv_rows, json_objects, ABANDONED_CSV_COLUMNS,
        fmt=args.format, out_path=out_path, delimiter=args.delimiter,
    )
    logger.info("abandoned-checkouts: %d record(s) -> %s", len(csv_rows), ", ".join(str(p) for p in written))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        logger.error("%s", exc)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
