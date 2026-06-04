"""Output writer tests (spec 13 / 16)."""

from __future__ import annotations

import csv
import json

from shopify_gap_filler.orders import ORDERS_CSV_COLUMNS
from shopify_gap_filler.output import write_csv, write_json, write_output

SAMPLE_ROWS = [
    {
        "order_id": "gid://shopify/Order/1",
        "name": "#1",
        "note": 'Has, comma and "quote"',
        "line_items_count": 2,
    },
    {"order_id": "gid://shopify/Order/2", "name": "#2", "note": "", "line_items_count": 0},
]

SAMPLE_OBJECTS = [
    {"order_id": "gid://shopify/Order/1", "totals": {"total_price": "10.00"}},
    {"order_id": "gid://shopify/Order/2", "totals": {"total_price": "20.00"}},
]


def test_write_csv_header_and_escaping(tmp_path):
    out = tmp_path / "orders.csv"
    write_csv(SAMPLE_ROWS, ORDERS_CSV_COLUMNS, out)
    text = out.read_text(encoding="utf-8")
    # Header present with all columns.
    first_line = text.splitlines()[0]
    assert first_line.split(",")[0] == "order_id"
    # Read it back and check escaping survived.
    with out.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert rows[0]["note"] == 'Has, comma and "quote"'
    assert rows[0]["line_items_count"] == "2"


def test_write_csv_custom_delimiter(tmp_path):
    out = tmp_path / "orders_semi.csv"
    write_csv(SAMPLE_ROWS, ORDERS_CSV_COLUMNS, out, delimiter=";")
    header = out.read_text(encoding="utf-8").splitlines()[0]
    assert ";" in header
    assert header.split(";")[0] == "order_id"


def test_write_json_structure(tmp_path):
    out = tmp_path / "orders.json"
    write_json(SAMPLE_OBJECTS, out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    assert loaded[0]["totals"]["total_price"] == "10.00"


def test_write_output_both_creates_two_files(tmp_path):
    base = tmp_path / "exports" / "orders_2025"
    written = write_output(
        SAMPLE_ROWS, SAMPLE_OBJECTS, ORDERS_CSV_COLUMNS, fmt="both", out_path=base
    )
    assert len(written) == 2
    csv_path = base.with_suffix(".csv")
    json_path = base.with_suffix(".json")
    assert csv_path.exists()
    assert json_path.exists()


def test_write_output_both_strips_existing_extension(tmp_path):
    # If user passes a .csv path with 'both', we still produce .csv and .json.
    out = tmp_path / "orders.csv"
    written = write_output(
        SAMPLE_ROWS, SAMPLE_OBJECTS, ORDERS_CSV_COLUMNS, fmt="both", out_path=out
    )
    names = sorted(p.name for p in written)
    assert names == ["orders.csv", "orders.json"]


def test_output_scrubs_pci_defensively(tmp_path):
    # Even if a card key sneaks into a row, output must not write it.
    rows = [{"order_id": "x", "creditCardNumber": "4111111111111111", "name": "#x"}]
    out = tmp_path / "leak.csv"
    write_csv(rows, ["order_id", "name", "creditCardNumber"], out)
    text = out.read_text(encoding="utf-8")
    assert "4111111111111111" not in text
    assert "creditCardNumber" not in text


def test_json_output_scrubs_pci(tmp_path):
    objs = [{"order_id": "x", "payment": {"paymentDetails": {"creditCardBin": "411111"}}}]
    out = tmp_path / "leak.json"
    write_json(objs, out)
    text = out.read_text(encoding="utf-8")
    assert "411111" not in text
    assert "paymentDetails" not in text
