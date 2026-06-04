"""PCI scrubbing tests — the critical anti-leak suite (spec 9.1 / 16)."""

from __future__ import annotations

import json

from shopify_gap_filler.security import PCI_DENYLIST, is_denied_key, scrub

DENIED_SAMPLE_KEYS = [
    "paymentDetails",
    "creditCardNumber",
    "credit_card_bin",
    "creditCardCompany",
    "cardBrand",
    "cvvResultCode",
    "avsResultCode",
    "expirationMonth",
    "expirationYear",
    "creditCardWallet",
]


def test_denylist_is_nonempty():
    assert len(PCI_DENYLIST) > 0


def test_is_denied_key_matches_card_fields():
    for key in DENIED_SAMPLE_KEYS:
        assert is_denied_key(key), f"{key} should be denied"


def test_account_number_is_allowed():
    # Masked accountNumber is explicitly preserved (spec 7 / 9.1).
    assert not is_denied_key("accountNumber")
    assert not is_denied_key("account_number")


def test_safe_keys_are_not_denied():
    for key in ["id", "gateway", "amountSet", "paymentId", "status", "kind", "test"]:
        assert not is_denied_key(key), f"{key} should be kept"


def test_scrub_removes_payment_details_from_fixture(orders_with_pci):
    cleaned = scrub(orders_with_pci)
    blob = json.dumps(cleaned)
    # No denylist token should survive anywhere in the structure.
    # NB: "1111" is intentionally NOT checked here because the masked
    # accountNumber ("•••• 1111") is deliberately preserved (see dedicated test).
    for token in ["paymentDetails", "creditCard", "credit_card", "cvv", "avs",
                  "expiration", "wallet", "411111"]:
        assert token not in blob, f"{token!r} leaked after scrub"


def test_scrub_preserves_account_number(orders_with_pci):
    cleaned = scrub(orders_with_pci)
    tx = cleaned["data"]["orders"]["edges"][0]["node"]["transactions"][0]
    assert tx["accountNumber"] == "•••• 1111"
    assert "paymentDetails" not in tx


def test_scrub_does_not_mutate_input(orders_with_pci):
    original = json.dumps(orders_with_pci, sort_keys=True)
    scrub(orders_with_pci)
    assert json.dumps(orders_with_pci, sort_keys=True) == original


def test_scrub_handles_nested_lists_and_scalars():
    obj = {
        "keep": [1, 2, {"card": "x", "ok": "y"}],
        "creditCardNumber": "1234",
        "nested": {"avsResultCode": "Y", "id": 5},
    }
    cleaned = scrub(obj)
    assert cleaned == {"keep": [1, 2, {"ok": "y"}], "nested": {"id": 5}}
