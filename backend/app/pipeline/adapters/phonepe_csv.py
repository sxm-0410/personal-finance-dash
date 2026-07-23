"""PhonePe CSV adapter.

CSV is the reliable path and doubles as the ground-truth oracle for scoring the
PDF parser (see scripts/reconcile.py). PhonePe's export headers vary, so we
match columns by fuzzy header name rather than fixed position.
"""
from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from app.pipeline.adapters.base import ParseResult, RawTransaction, UnparsedLine

# Candidate header names (lowercased, stripped) mapped to canonical fields.
_HEADER_ALIASES = {
    "date": {"date", "transaction date", "txn date"},
    "time": {"time", "transaction time"},
    "details": {
        "transaction details", "details", "description", "narration",
        "particulars", "to / from", "merchant", "paid to",
    },
    "type": {"type", "transaction type", "debit/credit", "dr/cr", "direction"},
    "amount": {"amount", "amount (inr)", "amount(inr)", "transaction amount"},
    "reference": {"utr", "reference", "reference no", "reference id",
                  "transaction id", "utr no"},
}

_DATE_FORMATS = [
    "%b %d, %Y", "%d %b %Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y",
    "%m/%d/%Y", "%d %B %Y", "%B %d, %Y",
]
_DATETIME_FORMATS = [f"{d} %I:%M %p" for d in _DATE_FORMATS] + [
    f"{d} %H:%M:%S" for d in _DATE_FORMATS
]


def _parse_dt(date_str: str, time_str: str | None) -> datetime | None:
    combined = f"{date_str} {time_str}".strip() if time_str else date_str.strip()
    for fmt in (_DATETIME_FORMATS if time_str else []) + _DATE_FORMATS:
        try:
            return datetime.strptime(combined, fmt)
        except ValueError:
            continue
    # Last resort: try the date alone even if a time was supplied.
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _parse_amount(raw: str) -> Decimal | None:
    cleaned = (
        raw.replace("₹", "").replace("Rs.", "").replace("Rs", "")
        .replace(",", "").replace("INR", "").strip()
    )
    if not cleaned:
        return None
    try:
        return abs(Decimal(cleaned))
    except InvalidOperation:
        return None


def _infer_direction(type_str: str, amount_raw: str) -> str | None:
    t = type_str.strip().lower()
    if t in {"debit", "dr", "debited", "paid", "sent", "-"}:
        return "debit"
    if t in {"credit", "cr", "credited", "received", "+"}:
        return "credit"
    # Fall back to a signed amount if the type column was empty.
    if amount_raw.strip().startswith("-"):
        return "debit"
    if amount_raw.strip().startswith("+"):
        return "credit"
    return None


class PhonePeCSVAdapter:
    name = "phonepe_csv"

    def sniff(self, path: Path) -> bool:
        if path.suffix.lower() != ".csv":
            return False
        try:
            with path.open(newline="", encoding="utf-8-sig") as fh:
                header = fh.readline().lower()
            return any(a in header for a in ("date", "amount", "transaction"))
        except OSError:
            return False

    def _map_columns(self, fieldnames: list[str]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for col in fieldnames:
            key = col.strip().lower()
            for canonical, aliases in _HEADER_ALIASES.items():
                if key in aliases and canonical not in mapping:
                    mapping[canonical] = col
        return mapping

    @staticmethod
    def _looks_like_header(row: list[str]) -> bool:
        cells = {c.strip().lower() for c in row}
        return "date" in cells and any("amount" in c for c in cells)

    def parse(self, path: Path, password: str | None = None) -> ParseResult:
        result = ParseResult(source_file=path.name)
        with path.open(newline="", encoding="utf-8-sig") as fh:
            all_rows = list(csv.reader(fh))

        # PhonePe CSVs carry a 1-2 line preamble ("Transaction Statement for…",
        # "Duration,…") before the real header. Skip until we find it.
        header_idx = next(
            (i for i, r in enumerate(all_rows) if self._looks_like_header(r)), None
        )
        if header_idx is None:
            result.unparsed.append(
                UnparsedLine("", "CSV header row (Date/Amount) not found")
            )
            return result

        fieldnames = [c.strip() for c in all_rows[header_idx]]
        data_rows = all_rows[header_idx + 1 :]
        reader = (dict(zip(fieldnames, r)) for r in data_rows if any(c.strip() for c in r))

        cols = self._map_columns(fieldnames)
        for missing in ("date", "amount"):
            if missing not in cols:
                result.unparsed.append(
                    UnparsedLine(
                        ",".join(fieldnames),
                        f"CSV missing required '{missing}' column",
                    )
                )
                return result

        for row in reader:
                raw_line = " | ".join(f"{k}={v}" for k, v in row.items())
                date_str = row.get(cols["date"], "") or ""
                time_str = row.get(cols.get("time", ""), "") if "time" in cols else None
                amount_raw = row.get(cols["amount"], "") or ""
                type_str = row.get(cols.get("type", ""), "") if "type" in cols else ""
                details = row.get(cols.get("details", ""), "") if "details" in cols else ""
                reference = (
                    row.get(cols.get("reference", ""), "")
                    if "reference" in cols else None
                )

                dt = _parse_dt(date_str, time_str)
                amount = _parse_amount(amount_raw)
                direction = _infer_direction(type_str, amount_raw)

                if dt is None or amount is None or direction is None:
                    reason = []
                    if dt is None:
                        reason.append("unparseable date")
                    if amount is None:
                        reason.append("unparseable amount")
                    if direction is None:
                        reason.append("unknown direction")
                    result.unparsed.append(UnparsedLine(raw_line, ", ".join(reason)))
                    continue

                txn: RawTransaction = {
                    "txn_date": dt,
                    "amount": amount,
                    "direction": direction,  # type: ignore[typeddict-item]
                    "counterparty_raw": details.strip() or "UNKNOWN",
                    "reference_id": (reference or "").strip() or None,
                    "source_app": "phonepe",
                    "parse_confidence": 1.0,
                    "raw_line": raw_line,
                }
                result.rows.append(txn)
        return result
