"""PhonePe PDF adapter.

The deliverable, and the brittle one. Strategy:
1. Decrypt if needed (PhonePe locks statements with a password) — never persist it.
2. Try table extraction per page (high confidence).
3. Fall back to text extraction + a date-anchored line regex (lower confidence).

Every produced row carries a parse_confidence so the reconciliation harness and
the UI can weight table-derived rows above regex-derived ones. Rows that can't
be parsed are returned in ParseResult.unparsed, never dropped.
"""
from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pdfplumber
from pypdf import PdfReader, PdfWriter

from app.pipeline.adapters.base import ParseResult, UnparsedLine

# A PhonePe statement row usually starts with a date like "Jan 05, 2024".
_DATE_ANCHOR = re.compile(
    r"^([A-Z][a-z]{2}\s+\d{1,2},?\s+\d{4})", re.MULTILINE
)
_TIME = re.compile(r"(\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?)")
_AMOUNT = re.compile(r"(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d{1,2})?)")
_DEBIT_WORDS = ("debit", "paid to", "payment to", "sent to", "money sent")
_CREDIT_WORDS = ("credit", "received from", "refund", "money received")

_DATE_FORMATS = ["%b %d, %Y", "%b %d %Y", "%B %d, %Y"]


def _decrypt_to_temp(path: Path, password: str) -> Path:
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt(password)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    tmp = path.with_suffix(".decrypted.pdf")
    with tmp.open("wb") as fh:
        writer.write(fh)
    return tmp


def _parse_date(s: str) -> datetime | None:
    s = s.replace(",", "").strip()
    for fmt in (f.replace(",", "") for f in _DATE_FORMATS):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _parse_amount(s: str) -> Decimal | None:
    try:
        return abs(Decimal(s.replace(",", "")))
    except InvalidOperation:
        return None


def _direction_from_text(text: str) -> str:
    low = text.lower()
    if any(w in low for w in _CREDIT_WORDS):
        return "credit"
    return "debit"  # PhonePe statements are debit-dominant; default to debit


class PhonePePDFAdapter:
    name = "phonepe_pdf"

    def sniff(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def parse(self, path: Path, password: str | None = None) -> ParseResult:
        result = ParseResult(source_file=path.name)
        work_path = path
        decrypted: Path | None = None
        try:
            reader = PdfReader(str(path))
            if reader.is_encrypted:
                if not password:
                    result.unparsed.append(
                        UnparsedLine(path.name, "PDF is encrypted; password required")
                    )
                    return result
                decrypted = _decrypt_to_temp(path, password)
                work_path = decrypted

            with pdfplumber.open(str(work_path)) as pdf:
                for page in pdf.pages:
                    got = self._parse_page_tables(page, result)
                    if not got:
                        self._parse_page_text(page, result)
        except Exception as exc:  # noqa: BLE001 - degrade gracefully per PRD
            result.unparsed.append(UnparsedLine(path.name, f"PDF error: {exc}"))
        finally:
            if decrypted and decrypted.exists():
                decrypted.unlink()  # never leave a decrypted copy on disk
        return result

    def _parse_page_tables(self, page, result: ParseResult) -> bool:
        tables = page.extract_tables() or []
        produced = False
        for table in tables:
            for row in table:
                cells = [(c or "").strip() for c in row]
                joined = " ".join(cells)
                dt_match = _DATE_ANCHOR.search(joined)
                amt_match = _AMOUNT.search(joined)
                if not dt_match or not amt_match:
                    continue
                dt = _parse_date(dt_match.group(1))
                amount = _parse_amount(amt_match.group(1))
                if dt is None or amount is None:
                    continue
                result.rows.append(
                    {
                        "txn_date": dt,
                        "amount": amount,
                        "direction": _direction_from_text(joined),  # type: ignore[typeddict-item]
                        "counterparty_raw": self._extract_counterparty(joined),
                        "reference_id": None,
                        "source_app": "phonepe",
                        "parse_confidence": 1.0,
                        "raw_line": joined,
                    }
                )
                produced = True
        return produced

    def _parse_page_text(self, page, result: ParseResult) -> None:
        text = page.extract_text() or ""
        # Split into records at each date anchor.
        positions = [m.start() for m in _DATE_ANCHOR.finditer(text)]
        if not positions:
            return
        positions.append(len(text))
        for i in range(len(positions) - 1):
            chunk = text[positions[i] : positions[i + 1]].strip()
            dt_match = _DATE_ANCHOR.search(chunk)
            amt_match = _AMOUNT.search(chunk)
            if not dt_match or not amt_match:
                result.unparsed.append(UnparsedLine(chunk[:200], "no date/amount in record"))
                continue
            dt = _parse_date(dt_match.group(1))
            amount = _parse_amount(amt_match.group(1))
            if dt is None or amount is None:
                result.unparsed.append(UnparsedLine(chunk[:200], "unparseable date/amount"))
                continue
            result.rows.append(
                {
                    "txn_date": dt,
                    "amount": amount,
                    "direction": _direction_from_text(chunk),  # type: ignore[typeddict-item]
                    "counterparty_raw": self._extract_counterparty(chunk),
                    "reference_id": None,
                    "source_app": "phonepe",
                    "parse_confidence": 0.7,  # regex fallback is less certain
                    "raw_line": chunk[:300],
                }
            )

    @staticmethod
    def _extract_counterparty(text: str) -> str:
        """Best-effort merchant: strip date/time/amount/keywords, keep the rest."""
        t = _DATE_ANCHOR.sub("", text)
        t = _TIME.sub("", t)
        t = _AMOUNT.sub("", t)
        t = re.sub(r"(?i)\b(debit|credit|paid to|received from|payment to)\b", "", t)
        t = re.sub(r"\s+", " ", t).strip(" -|,")
        return t[:120] or "UNKNOWN"
