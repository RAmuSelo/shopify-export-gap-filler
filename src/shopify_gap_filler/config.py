"""Configuration loading and validation.

Reads credentials from a ``.env`` file (simple in-house parser, no hard
dependency on python-dotenv) and from the process environment. Validates the
required values and never logs the token.

LOCKED spec: default API version is ``2026-04`` (latest stable). It can be
overridden by ``SHOPIFY_API_VERSION`` (env) and then by ``--api-version`` (CLI).
Any value matching ``^\\d{4}-\\d{2}$`` is accepted; the DEFAULT stays 2026-04.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# Default Shopify Admin API version (LOCKED spec section 1 / 3). Latest stable.
DEFAULT_API_VERSION = "2026-04"

# Accepted API version shape: four digits, dash, two digits (e.g. 2026-04).
_API_VERSION_RE = re.compile(r"^\d{4}-\d{2}$")

# Default leaky-bucket / backoff knobs (overridable via env).
DEFAULT_MAX_RETRIES = 5
DEFAULT_TIMEOUT_SECONDS = 30


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass
class Config:
    """Validated runtime configuration."""

    shop: str
    api_token: str
    api_version: str = DEFAULT_API_VERSION
    max_retries: int = DEFAULT_MAX_RETRIES
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    @property
    def endpoint(self) -> str:
        """Full GraphQL endpoint URL for this shop + version."""
        return (
            f"https://{self.shop}.myshopify.com"
            f"/admin/api/{self.api_version}/graphql.json"
        )

    def masked_token(self) -> str:
        """A safe, non-reversible representation of the token for logging."""
        return mask_token(self.api_token)

    def __repr__(self) -> str:  # never leak the token via repr
        return (
            f"Config(shop={self.shop!r}, api_version={self.api_version!r}, "
            f"api_token={self.masked_token()!r}, "
            f"max_retries={self.max_retries!r})"
        )


def mask_token(token: str | None) -> str:
    """Return a masked token suitable for logs (never the raw value)."""
    if not token:
        return "<unset>"
    if len(token) <= 4:
        return "****"
    return f"{token[:4]}…{'*' * 6}"


def parse_env_file(path: str | Path) -> dict[str, str]:
    """Minimal ``.env`` parser.

    Supports ``KEY=VALUE`` lines, ``#`` comments, blank lines, optional
    ``export`` prefix, and surrounding single/double quotes on the value.
    Returns a dict; missing file returns an empty dict (not an error).
    """
    path = Path(path)
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            result[key] = value
    return result


def validate_api_version(value: str) -> str:
    """Validate an API version string; raise ConfigError if malformed."""
    if not _API_VERSION_RE.match(value):
        raise ConfigError(
            f"Invalid API version {value!r}. Expected format YYYY-MM "
            f"(e.g. {DEFAULT_API_VERSION})."
        )
    return value


def load_config(
    env_path: str | Path = ".env",
    *,
    environ: dict[str, str] | None = None,
    api_version_override: str | None = None,
) -> Config:
    """Build and validate a :class:`Config`.

    Resolution order for each value: explicit override (CLI) > process env >
    ``.env`` file > default. The process environment takes precedence over the
    ``.env`` file so that ``SHOPIFY_API_VERSION=… python -m …`` works as
    expected.
    """
    environ = dict(os.environ if environ is None else environ)
    file_values = parse_env_file(env_path)

    def get(key: str) -> str | None:
        if key in environ and environ[key] != "":
            return environ[key]
        if key in file_values and file_values[key] != "":
            return file_values[key]
        return None

    shop = get("SHOPIFY_SHOP")
    token = get("SHOPIFY_ADMIN_API_TOKEN")

    missing = [
        name
        for name, val in (
            ("SHOPIFY_SHOP", shop),
            ("SHOPIFY_ADMIN_API_TOKEN", token),
        )
        if not val
    ]
    if missing:
        raise ConfigError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". Set them in your environment or in a .env file "
            "(see .env.example). Never commit real secrets."
        )

    # Normalise shop: accept either "my-store" or "my-store.myshopify.com".
    assert shop is not None  # for type-checkers; guarded by `missing` above
    shop = shop.strip()
    if shop.endswith(".myshopify.com"):
        shop = shop[: -len(".myshopify.com")]

    # API version resolution: CLI override > env/.env > default.
    version = api_version_override or get("SHOPIFY_API_VERSION") or DEFAULT_API_VERSION
    version = validate_api_version(version.strip())

    max_retries = _int_or_default(get("SHOPIFY_MAX_RETRIES"), DEFAULT_MAX_RETRIES)
    timeout = _int_or_default(get("SHOPIFY_TIMEOUT_SECONDS"), DEFAULT_TIMEOUT_SECONDS)

    assert token is not None  # guarded by `missing` above
    return Config(
        shop=shop,
        api_token=token.strip(),
        api_version=version,
        max_retries=max_retries,
        timeout_seconds=timeout,
    )


def _int_or_default(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
