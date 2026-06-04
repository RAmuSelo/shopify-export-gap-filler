"""Rate-limit / backoff tests (spec 12 / 16). Zero network, no real sleep."""

from __future__ import annotations

import pytest

from shopify_gap_filler.client import GraphQLError, ShopifyGraphQLClient

THROTTLED_RESPONSE = {
    "errors": [
        {
            "message": "Throttled",
            "extensions": {
                "code": "THROTTLED",
            },
        }
    ],
    "extensions": {
        "cost": {
            "requestedQueryCost": 100,
            "throttleStatus": {
                "maximumAvailable": 1000,
                "currentlyAvailable": 40,
                "restoreRate": 50,
            },
        }
    },
}

OK_RESPONSE = {"data": {"orders": {"pageInfo": {"hasNextPage": False}, "edges": []}}}


def _record_sleep():
    calls: list[float] = []

    def _sleep(seconds: float) -> None:
        calls.append(seconds)

    return calls, _sleep


def test_retries_on_graphql_throttled_then_succeeds(fake_config, make_transport):
    transport = make_transport([(200, THROTTLED_RESPONSE), (200, OK_RESPONSE)])
    sleeps, sleep_fn = _record_sleep()
    client = ShopifyGraphQLClient(fake_config, transport=transport, sleep=sleep_fn)
    data = client.execute("query { x }", {})
    assert "orders" in data
    assert len(transport.calls) == 2
    assert len(sleeps) == 1  # one backoff between the two attempts


def test_retries_on_http_429_then_succeeds(fake_config, make_transport):
    transport = make_transport([(429, {"errors": [{"message": "rate"}]}), (200, OK_RESPONSE)])
    sleeps, sleep_fn = _record_sleep()
    client = ShopifyGraphQLClient(fake_config, transport=transport, sleep=sleep_fn)
    data = client.execute("query { x }", {})
    assert "orders" in data
    assert len(sleeps) == 1


def test_retries_on_5xx_then_succeeds(fake_config, make_transport):
    transport = make_transport([(503, {}), (200, OK_RESPONSE)])
    sleeps, sleep_fn = _record_sleep()
    client = ShopifyGraphQLClient(fake_config, transport=transport, sleep=sleep_fn)
    data = client.execute("query { x }", {})
    assert "orders" in data
    assert len(sleeps) == 1


def test_no_retry_on_400(fake_config, make_transport):
    transport = make_transport([(400, {"errors": [{"message": "bad request"}]})])
    sleeps, sleep_fn = _record_sleep()
    client = ShopifyGraphQLClient(fake_config, transport=transport, sleep=sleep_fn)
    with pytest.raises(GraphQLError):
        client.execute("query { x }", {})
    assert len(transport.calls) == 1  # no retry
    assert len(sleeps) == 0


def test_gives_up_after_max_retries(fake_config, make_transport):
    # fake_config.max_retries == 3 -> 1 initial + 3 retries = 4 attempts, all throttled.
    responses = [(429, {}) for _ in range(10)]
    transport = make_transport(responses)
    sleeps, sleep_fn = _record_sleep()
    client = ShopifyGraphQLClient(fake_config, transport=transport, sleep=sleep_fn)
    with pytest.raises(GraphQLError):
        client.execute("query { x }", {})
    assert len(transport.calls) == fake_config.max_retries + 1
    assert len(sleeps) == fake_config.max_retries


def test_throttle_status_recorded(fake_config, make_transport):
    transport = make_transport([(200, THROTTLED_RESPONSE), (200, OK_RESPONSE)])
    sleeps, sleep_fn = _record_sleep()
    client = ShopifyGraphQLClient(fake_config, transport=transport, sleep=sleep_fn)
    client.execute("query { x }", {})
    assert client.last_throttle_status is not None
    assert client.last_throttle_status["restoreRate"] == 50
