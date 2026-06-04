"""Defensive PCI scrubbing (LOCKED spec section 9.1).

Even though the GraphQL queries never request card / PCI fields, this module
applies a denylist by key name to every API response *before* anything is
written or logged. This is defense in depth: if a future query edit, a schema
change, or an unexpected server response ever surfaced a sensitive key, it is
stripped here.

The denylist is matched case-insensitively as a substring of the key name, so
``creditCard``, ``credit_card``, ``CardPaymentDetails`` and ``cvvResultCode``
all match.

IMPORTANT nuance on "number":
- ``accountNumber`` on OrderTransaction is explicitly masked by Shopify and is
  NOT card data, so it is preserved (it is on the allowlist below).
- Any other ``*number*`` key that also looks like card data (e.g.
  ``creditCardNumber``) is removed because it matches a card token first.
"""

from __future__ import annotations

from typing import Any

# Substrings that mark a key as PCI / sensitive payment data. Matched
# case-insensitively against the key name.
PCI_DENYLIST: tuple[str, ...] = (
    "paymentdetails",      # OrderTransaction.paymentDetails union (whole subtree)
    "credit_card",
    "creditcard",
    "card",                # CardPaymentDetails.* and any *card* key
    "cvv",
    "avs",                 # avsResultCode
    "cvvresultcode",
    "avsresultcode",
    "bin",                 # credit_card_bin / card bin
    "expiration",          # expirationMonth / expirationYear
    "wallet",
)

# Keys that contain a denylist substring but are explicitly safe and must be
# kept. Matched case-insensitively against the *exact* key name.
PCI_ALLOWLIST_EXACT: frozenset[str] = frozenset(
    {
        "accountnumber",   # masked by Shopify, not card data (spec 7 / 9.1)
    }
)


def is_denied_key(key: str) -> bool:
    """Return True if ``key`` should be removed as PCI / sensitive."""
    lowered = key.lower()
    if lowered in PCI_ALLOWLIST_EXACT:
        return False
    return any(token in lowered for token in PCI_DENYLIST)


def scrub(obj: Any) -> Any:
    """Recursively remove every denied key from a nested structure.

    Returns a NEW structure; the input is not mutated. Works on dicts, lists,
    tuples and scalars. Dict keys are coerced to ``str`` for matching.
    """
    if isinstance(obj, dict):
        cleaned: dict[Any, Any] = {}
        for key, value in obj.items():
            if isinstance(key, str) and is_denied_key(key):
                continue
            cleaned[key] = scrub(value)
        return cleaned
    if isinstance(obj, list):
        return [scrub(item) for item in obj]
    if isinstance(obj, tuple):
        return tuple(scrub(item) for item in obj)
    return obj
