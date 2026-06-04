"""Shared pytest fixtures.

Inserts ``src/`` into ``sys.path`` so the package imports without installation.
Provides synthetic GraphQL fixture loaders and a fake HTTP transport so the
whole suite runs with ZERO network access.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# --- make src/ importable without installing the package ---------------------
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def load_fixture(name: str) -> dict:
    """Load a JSON fixture by file name (with or without .json)."""
    if not name.endswith(".json"):
        name = f"{name}.json"
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def orders_page1() -> dict:
    return load_fixture("orders_page1")


@pytest.fixture
def orders_page2() -> dict:
    return load_fixture("orders_page2")


@pytest.fixture
def orders_with_pci() -> dict:
    return load_fixture("orders_with_pci")


@pytest.fixture
def abandoned_checkouts() -> dict:
    return load_fixture("abandoned_checkouts")


class FakeTransport:
    """A scripted transport for ShopifyGraphQLClient.

    Each call returns the next (status, payload) tuple from ``responses``.
    Records every (url, headers, body) it was called with for assertions.
    Never touches the network.
    """

    def __init__(self, responses: list[tuple[int, dict]]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, headers, json_body, timeout):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "body": json_body,
                "timeout": timeout,
            }
        )
        if not self._responses:
            raise AssertionError("FakeTransport ran out of scripted responses")
        return self._responses.pop(0)


@pytest.fixture
def make_transport():
    """Factory: build a FakeTransport from a list of (status, payload)."""

    def _factory(responses: list[tuple[int, dict]]) -> FakeTransport:
        return FakeTransport(responses)

    return _factory


@pytest.fixture
def fake_config():
    """A Config that points at a fake store with a placeholder token."""
    from shopify_gap_filler.config import Config

    return Config(
        shop="example-store",
        api_token="shpat_fake_token_for_tests",
        api_version="2026-04",
        max_retries=3,
        timeout_seconds=5,
    )


@pytest.fixture
def no_sleep():
    """A no-op sleep so backoff tests run instantly."""

    def _sleep(_seconds: float) -> None:
        return None

    return _sleep
