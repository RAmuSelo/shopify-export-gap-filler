"""CLI argument parsing tests (spec 15 / 16). No network."""

from __future__ import annotations

import pytest

from shopify_gap_filler import cli


def test_parser_exposes_both_subcommands():
    parser = cli.build_parser()
    # Parse each subcommand with minimal args.
    ns_orders = parser.parse_args(["orders", "--since", "2025-01-01"])
    assert ns_orders.command == "orders"
    assert ns_orders.since == "2025-01-01"
    assert ns_orders.format == "csv"  # default

    ns_ac = parser.parse_args(["abandoned-checkouts", "--format", "json"])
    assert ns_ac.command == "abandoned-checkouts"
    assert ns_ac.format == "json"


def test_orders_has_no_transactions_flag():
    parser = cli.build_parser()
    ns = parser.parse_args(["orders", "--no-transactions"])
    assert ns.no_transactions is True
    ns2 = parser.parse_args(["orders"])
    assert ns2.no_transactions is False


def test_common_options_parsed():
    parser = cli.build_parser()
    ns = parser.parse_args(
        [
            "orders",
            "--since", "2024-01-01",
            "--until", "2024-12-31",
            "--limit", "100",
            "--api-version", "2026-04",
            "--format", "both",
            "--out", "exports/orders",
            "--delimiter", ";",
        ]
    )
    assert ns.limit == 100
    assert ns.api_version == "2026-04"
    assert ns.until == "2024-12-31"
    assert ns.out == "exports/orders"
    assert ns.delimiter == ";"


def test_missing_subcommand_errors():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_invalid_format_rejected():
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["orders", "--format", "xml"])


def test_build_date_filter():
    assert cli.build_date_filter("2025-01-01", None) == "created_at:>=2025-01-01"
    assert cli.build_date_filter(None, "2025-12-31") == "created_at:<=2025-12-31"
    assert (
        cli.build_date_filter("2025-01-01", "2025-12-31")
        == "created_at:>=2025-01-01 created_at:<=2025-12-31"
    )
    assert cli.build_date_filter(None, None) is None


FAKE_TOKEN = "shpat_fake_test_token"


def _set_fake_creds(monkeypatch):
    monkeypatch.setenv("SHOPIFY_SHOP", "example.myshopify.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_API_TOKEN", FAKE_TOKEN)
    monkeypatch.delenv("SHOPIFY_API_VERSION", raising=False)


def _clear_creds(monkeypatch):
    for var in ("SHOPIFY_SHOP", "SHOPIFY_ADMIN_API_TOKEN", "SHOPIFY_API_VERSION"):
        monkeypatch.delenv(var, raising=False)


def test_dry_run_orders_validates_config_then_no_network(capsys, monkeypatch, tmp_path):
    # New rule: --dry-run validates config (creds) but performs NO network call.
    def _boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("network must not be touched in --dry-run")

    monkeypatch.setattr(cli, "ShopifyGraphQLClient", _boom)
    _set_fake_creds(monkeypatch)
    rc = cli.main([
        "orders", "--since", "2025-01-01", "--dry-run",
        "--env-file", str(tmp_path / "nope.env"),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "GapFillerOrders" in out
    assert "created_at:>=2025-01-01" in out
    assert FAKE_TOKEN not in out  # token is never displayed


def test_dry_run_abandoned_validates_config_then_no_network(capsys, monkeypatch, tmp_path):
    def _boom(*args, **kwargs):  # pragma: no cover
        raise AssertionError("network must not be touched in --dry-run")

    monkeypatch.setattr(cli, "ShopifyGraphQLClient", _boom)
    _set_fake_creds(monkeypatch)
    rc = cli.main([
        "abandoned-checkouts", "--since", "2025-06-01", "--dry-run",
        "--env-file", str(tmp_path / "nope.env"),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out
    assert "GapFillerAbandonedCheckouts" in out
    assert FAKE_TOKEN not in out


def test_dry_run_orders_no_transactions_omits_block(capsys, monkeypatch, tmp_path):
    _set_fake_creds(monkeypatch)
    rc = cli.main([
        "orders", "--dry-run", "--no-transactions",
        "--env-file", str(tmp_path / "nope.env"),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "transactions {" not in out


def test_dry_run_orders_without_credentials_exits_2(capsys, monkeypatch, tmp_path, caplog):
    import logging

    _clear_creds(monkeypatch)
    with caplog.at_level(logging.ERROR):
        rc = cli.main(["orders", "--dry-run", "--env-file", str(tmp_path / "nope.env")])
    assert rc == 2
    assert "Missing required configuration" in caplog.text
    assert FAKE_TOKEN not in capsys.readouterr().out


def test_dry_run_abandoned_without_credentials_exits_2(monkeypatch, tmp_path, caplog):
    import logging

    _clear_creds(monkeypatch)
    with caplog.at_level(logging.ERROR):
        rc = cli.main(["abandoned-checkouts", "--dry-run", "--env-file", str(tmp_path / "nope.env")])
    assert rc == 2
    assert "Missing required configuration" in caplog.text


def test_invalid_limit_exits(monkeypatch):
    def _boom(*args, **kwargs):  # pragma: no cover
        raise AssertionError("must not reach config with bad limit")

    monkeypatch.setattr(cli, "load_config", _boom)
    with pytest.raises(SystemExit):
        cli.main(["orders", "--limit", "0", "--dry-run"])


def test_missing_config_returns_exit_code_2(tmp_path, monkeypatch):
    # Real (non-dry) run with no credentials -> ConfigError -> rc 2.
    # Hermetic: clear any Shopify vars that might exist in the real environment.
    for var in (
        "SHOPIFY_SHOP",
        "SHOPIFY_ADMIN_API_TOKEN",
        "SHOPIFY_API_VERSION",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    rc = cli.main(["orders", "--since", "2025-01-01", "--env-file", str(tmp_path / ".env")])
    assert rc == 2
