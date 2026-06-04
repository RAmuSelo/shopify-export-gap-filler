"""Configuration tests (spec 1 / 3 / 16)."""

from __future__ import annotations

import logging

import pytest

from shopify_gap_filler.config import (
    DEFAULT_API_VERSION,
    Config,
    ConfigError,
    load_config,
    mask_token,
    parse_env_file,
    validate_api_version,
)


def test_default_api_version_is_2026_04():
    assert DEFAULT_API_VERSION == "2026-04"


def test_missing_credentials_raise_clear_error(tmp_path):
    missing_env = tmp_path / ".env"  # does not exist
    with pytest.raises(ConfigError) as exc:
        load_config(missing_env, environ={})
    msg = str(exc.value)
    assert "SHOPIFY_SHOP" in msg
    assert "SHOPIFY_ADMIN_API_TOKEN" in msg


def test_load_from_env_dict_applies_default_version(tmp_path):
    cfg = load_config(
        tmp_path / ".env",
        environ={
            "SHOPIFY_SHOP": "example-store",
            "SHOPIFY_ADMIN_API_TOKEN": "shpat_fake_xyz",
        },
    )
    assert cfg.shop == "example-store"
    assert cfg.api_version == "2026-04"


def test_env_var_overrides_version(tmp_path):
    cfg = load_config(
        tmp_path / ".env",
        environ={
            "SHOPIFY_SHOP": "example-store",
            "SHOPIFY_ADMIN_API_TOKEN": "shpat_fake_xyz",
            "SHOPIFY_API_VERSION": "2026-07",
        },
    )
    assert cfg.api_version == "2026-07"


def test_cli_override_beats_env(tmp_path):
    cfg = load_config(
        tmp_path / ".env",
        environ={
            "SHOPIFY_SHOP": "example-store",
            "SHOPIFY_ADMIN_API_TOKEN": "shpat_fake_xyz",
            "SHOPIFY_API_VERSION": "2026-07",
        },
        api_version_override="2026-04",
    )
    assert cfg.api_version == "2026-04"


def test_shop_suffix_is_stripped(tmp_path):
    cfg = load_config(
        tmp_path / ".env",
        environ={
            "SHOPIFY_SHOP": "example-store.myshopify.com",
            "SHOPIFY_ADMIN_API_TOKEN": "shpat_fake_xyz",
        },
    )
    assert cfg.shop == "example-store"
    assert cfg.endpoint == (
        "https://example-store.myshopify.com/admin/api/2026-04/graphql.json"
    )


def test_invalid_api_version_rejected():
    with pytest.raises(ConfigError):
        validate_api_version("nope")
    with pytest.raises(ConfigError):
        validate_api_version("2026")
    assert validate_api_version("2026-04") == "2026-04"


def test_any_well_formed_version_accepted():
    # The DEFAULT is 2026-04, but any well-formed override is accepted.
    assert validate_api_version("2030-01") == "2030-01"


def test_mask_token_never_returns_raw():
    raw = "shpat_supersecretvalue123456"
    masked = mask_token(raw)
    assert raw not in masked
    assert masked.startswith("shpa")
    assert mask_token("") == "<unset>"
    assert mask_token(None) == "<unset>"


def test_config_repr_does_not_leak_token():
    cfg = Config(shop="example-store", api_token="shpat_supersecret_value")
    assert "shpat_supersecret_value" not in repr(cfg)


def test_token_never_logged(tmp_path, caplog):
    cfg = load_config(
        tmp_path / ".env",
        environ={
            "SHOPIFY_SHOP": "example-store",
            "SHOPIFY_ADMIN_API_TOKEN": "shpat_supersecret_value",
        },
    )
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("shopify_gap_filler").info(
            "Using %s", cfg.masked_token()
        )
        logging.getLogger("shopify_gap_filler").debug("Config is %r", cfg)
    assert "shpat_supersecret_value" not in caplog.text


def test_parse_env_file_handles_quotes_comments_export(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "\n".join(
            [
                "# a comment",
                "",
                "SHOPIFY_SHOP=example-store",
                'export SHOPIFY_ADMIN_API_TOKEN="shpat_quoted"',
                "SHOPIFY_API_VERSION='2026-04'",
                "MALFORMED_LINE_NO_EQUALS",
            ]
        ),
        encoding="utf-8",
    )
    values = parse_env_file(p)
    assert values["SHOPIFY_SHOP"] == "example-store"
    assert values["SHOPIFY_ADMIN_API_TOKEN"] == "shpat_quoted"
    assert values["SHOPIFY_API_VERSION"] == "2026-04"
    assert "MALFORMED_LINE_NO_EQUALS" not in values


def test_env_takes_precedence_over_file(tmp_path):
    p = tmp_path / ".env"
    p.write_text(
        "SHOPIFY_SHOP=from-file\nSHOPIFY_ADMIN_API_TOKEN=shpat_file\n",
        encoding="utf-8",
    )
    cfg = load_config(
        p,
        environ={"SHOPIFY_SHOP": "from-env", "SHOPIFY_ADMIN_API_TOKEN": "shpat_env"},
    )
    assert cfg.shop == "from-env"
