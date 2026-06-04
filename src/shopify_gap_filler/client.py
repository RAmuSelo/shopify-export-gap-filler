"""GraphQL Admin API client.

Responsibilities (LOCKED spec sections 11 + 12):
- POST a GraphQL document to ``/admin/api/{version}/graphql.json`` with the
  ``X-Shopify-Access-Token`` header.
- Retry with exponential backoff + jitter on HTTP 429, HTTP 5xx, and GraphQL
  ``THROTTLED`` errors (``extensions.code``).
- Do NOT retry on other 4xx (explicit failure).
- Read ``extensions.cost.throttleStatus`` when present (proactive throttle is
  applied by callers that loop over pages).
- Never log the token (it is masked).

The actual network transport is injectable (``transport=`` argument) so the
test suite can run with zero network access. The default transport uses
``requests`` and is only imported lazily, so importing this module never
requires ``requests`` to be installed (tests inject a fake transport).
"""

from __future__ import annotations

import logging
import math
import random
import time
from typing import Any, Callable, Mapping

from .config import Config, mask_token

logger = logging.getLogger("shopify_gap_filler.client")

# A transport takes (url, headers, json_body, timeout) and returns
# (http_status:int, response_json:dict). It must not raise on HTTP error
# status; it should return the status so the client can decide.
Transport = Callable[[str, Mapping[str, str], dict, int], "tuple[int, dict]"]


class GraphQLError(Exception):
    """Raised for non-retryable GraphQL or HTTP errors."""


class ThrottledError(Exception):
    """Internal signal that a request was throttled and may be retried."""


def _requests_transport(
    url: str, headers: Mapping[str, str], json_body: dict, timeout: int
) -> "tuple[int, dict]":
    """Default transport backed by the ``requests`` library (lazy import)."""
    import requests  # imported lazily so tests need no network / no requests

    resp = requests.post(url, headers=dict(headers), json=json_body, timeout=timeout)
    try:
        payload = resp.json()
    except ValueError:
        payload = {"errors": [{"message": f"Non-JSON response (HTTP {resp.status_code})"}]}
    return resp.status_code, payload


class ShopifyGraphQLClient:
    """Minimal, sequential GraphQL client with throttle-aware backoff."""

    def __init__(
        self,
        config: Config,
        *,
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
    ) -> None:
        self.config = config
        self._transport = transport or _requests_transport
        self._sleep = sleep
        self._base_backoff = base_backoff
        self._max_backoff = max_backoff
        # Most recent throttleStatus seen, for proactive throttling by callers.
        self.last_throttle_status: dict[str, Any] | None = None
        self.last_cost: dict[str, Any] | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Shopify-Access-Token": self.config.api_token,
        }

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict:
        """Execute a GraphQL document and return its ``data`` payload.

        Retries on 429 / 5xx / THROTTLED up to ``config.max_retries``. Raises
        :class:`GraphQLError` on non-retryable errors or after exhausting
        retries.
        """
        body = {"query": query, "variables": variables or {}}
        attempt = 0
        while True:
            try:
                return self._execute_once(body)
            except ThrottledError as exc:
                if attempt >= self.config.max_retries:
                    raise GraphQLError(
                        f"Exhausted retries ({self.config.max_retries}) after "
                        f"throttling/transient errors: {exc}"
                    ) from exc
                delay = self._backoff_delay(attempt, hint=getattr(exc, "retry_after", None))
                logger.warning(
                    "Throttled/transient (attempt %d/%d); sleeping %.2fs. token=%s",
                    attempt + 1,
                    self.config.max_retries,
                    delay,
                    mask_token(self.config.api_token),
                )
                self._sleep(delay)
                attempt += 1

    def _execute_once(self, body: dict) -> dict:
        status, payload = self._transport(
            self.config.endpoint, self._headers, body, self.config.timeout_seconds
        )

        # Capture cost / throttle info if present (for proactive throttling).
        cost = (payload.get("extensions") or {}).get("cost") if isinstance(payload, dict) else None
        if isinstance(cost, dict):
            self.last_cost = cost
            throttle = cost.get("throttleStatus")
            if isinstance(throttle, dict):
                self.last_throttle_status = throttle

        # HTTP-level handling.
        if status == 429:
            exc = ThrottledError("HTTP 429 Too Many Requests")
            exc.retry_after = self._retry_after_seconds(payload)  # type: ignore[attr-defined]
            raise exc
        if 500 <= status < 600:
            raise ThrottledError(f"HTTP {status} server error")
        if status >= 400:
            # Other 4xx: explicit, non-retryable failure.
            raise GraphQLError(f"HTTP {status}: {_short_errors(payload)}")

        # GraphQL-level error handling.
        errors = payload.get("errors") if isinstance(payload, dict) else None
        if errors:
            if _has_throttled_code(errors):
                exc = ThrottledError(f"GraphQL THROTTLED: {_short_errors(payload)}")
                exc.retry_after = self._throttle_wait_hint()  # type: ignore[attr-defined]
                raise exc
            raise GraphQLError(f"GraphQL errors: {_short_errors(payload)}")

        data = payload.get("data") if isinstance(payload, dict) else None
        if data is None:
            raise GraphQLError(f"GraphQL response had no data: {_short_errors(payload)}")
        return data

    def _backoff_delay(self, attempt: int, hint: float | None = None) -> float:
        """Exponential backoff with full jitter, optionally floored by a hint."""
        capped = min(self._max_backoff, self._base_backoff * (2 ** attempt))
        delay = random.uniform(0, capped)
        if hint is not None:
            delay = max(delay, hint)
        return min(delay, self._max_backoff)

    def _throttle_wait_hint(self) -> float | None:
        """Compute a wait from the last throttleStatus, if available.

        Waits long enough to restore at least one query's worth of points based
        on ``restoreRate`` (spec 12, proactive throttle).
        """
        throttle = self.last_throttle_status
        cost = self.last_cost
        if not isinstance(throttle, dict) or not isinstance(cost, dict):
            return None
        restore_rate = throttle.get("restoreRate")
        currently = throttle.get("currentlyAvailable")
        requested = cost.get("requestedQueryCost")
        if not (isinstance(restore_rate, (int, float)) and restore_rate > 0):
            return None
        if not isinstance(currently, (int, float)) or not isinstance(requested, (int, float)):
            return None
        deficit = requested - currently
        if deficit <= 0:
            return None
        return math.ceil(deficit / restore_rate)

    @staticmethod
    def _retry_after_seconds(payload: dict) -> float | None:
        """Best-effort Retry-After parsed from a JSON error body, if echoed."""
        if not isinstance(payload, dict):
            return None
        value = payload.get("retry_after") or payload.get("Retry-After")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None


def _has_throttled_code(errors: Any) -> bool:
    if not isinstance(errors, list):
        return False
    for err in errors:
        if not isinstance(err, dict):
            continue
        code = (err.get("extensions") or {}).get("code")
        if isinstance(code, str) and code.upper() == "THROTTLED":
            return True
        message = err.get("message")
        if isinstance(message, str) and "throttled" in message.lower():
            return True
    return False


def _short_errors(payload: Any, limit: int = 240) -> str:
    if not isinstance(payload, dict):
        return str(payload)[:limit]
    errors = payload.get("errors")
    if errors:
        try:
            messages = [
                e.get("message", str(e)) if isinstance(e, dict) else str(e)
                for e in errors
            ]
            return "; ".join(messages)[:limit]
        except Exception:  # pragma: no cover - defensive
            return str(errors)[:limit]
    return str(payload)[:limit]
