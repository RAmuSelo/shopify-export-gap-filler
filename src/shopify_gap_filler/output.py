"""Output writers: CSV and JSON (LOCKED spec section 13).

- CSV: UTF-8, configurable delimiter (default ``,``), header always written,
  values quoted when they contain the delimiter / quotes / newlines.
- JSON: pretty, UTF-8, non-ASCII preserved.
- ``--format both`` writes ``<base>.csv`` and ``<base>.json``.

As a final defense-in-depth pass, everything is scrubbed again here before it
hits disk, so no PCI key can ever be written regardless of caller.
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Sequence

from .security import is_denied_key, scrub

logger = logging.getLogger("shopify_gap_filler.output")


def write_csv(
    rows: Sequence[dict[str, Any]],
    columns: Sequence[str],
    out_path: str | Path,
    *,
    delimiter: str = ",",
) -> Path:
    """Write rows to a CSV file with a fixed column order. Returns the path."""
    out_path = Path(out_path)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    safe_rows = [scrub(r) for r in rows]
    # Defense in depth: never even emit a denied column NAME in the header.
    safe_columns = [c for c in columns if not is_denied_key(str(c))]
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=safe_columns,
            delimiter=delimiter,
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for row in safe_rows:
            writer.writerow({col: _csv_cell(row.get(col, "")) for col in safe_columns})
    logger.info("wrote %d row(s) to %s", len(safe_rows), out_path)
    return out_path


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_json(objects: Sequence[dict[str, Any]], out_path: str | Path) -> Path:
    """Write a list of objects to a JSON file. Returns the path."""
    out_path = Path(out_path)
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    safe_objects = [scrub(o) for o in objects]
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(safe_objects, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    logger.info("wrote %d object(s) to %s", len(safe_objects), out_path)
    return out_path


def _split_base(out_path: str | Path) -> Path:
    """Strip a trailing .csv/.json extension to get the 'both' base path."""
    p = Path(out_path)
    if p.suffix.lower() in (".csv", ".json"):
        return p.with_suffix("")
    return p


def write_output(
    csv_rows: Sequence[dict[str, Any]],
    json_objects: Sequence[dict[str, Any]],
    columns: Sequence[str],
    *,
    fmt: str,
    out_path: str | Path,
    delimiter: str = ",",
) -> list[Path]:
    """Dispatch writing according to ``fmt`` (csv | json | both).

    Returns the list of paths written.
    """
    written: list[Path] = []
    if fmt == "csv":
        written.append(write_csv(csv_rows, columns, out_path, delimiter=delimiter))
    elif fmt == "json":
        written.append(write_json(json_objects, out_path))
    elif fmt == "both":
        base = _split_base(out_path)
        written.append(
            write_csv(csv_rows, columns, base.with_suffix(".csv"), delimiter=delimiter)
        )
        written.append(write_json(json_objects, base.with_suffix(".json")))
    else:  # pragma: no cover - guarded by argparse choices
        raise ValueError(f"Unknown format: {fmt!r}")
    return written
