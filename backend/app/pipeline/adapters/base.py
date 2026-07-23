"""Source-adapter interface.

One narrow protocol, many implementations. A PhonePe CSV, a PhonePe PDF, and
(later) a GPay/Paytm export all produce the same RawTransaction shape, so
everything downstream is source-agnostic.

Golden rule: never silently drop a row. Anything that fails to parse goes into
`ParseResult.unparsed` with a reason, which becomes the UI review queue.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Protocol, TypedDict

Direction = Literal["debit", "credit"]


class RawTransaction(TypedDict):
    txn_date: datetime
    amount: Decimal
    direction: Direction
    counterparty_raw: str
    reference_id: str | None
    source_app: str
    parse_confidence: float
    raw_line: str


@dataclass
class UnparsedLine:
    raw_line: str
    reason: str


@dataclass
class ParseResult:
    rows: list[RawTransaction] = field(default_factory=list)
    unparsed: list[UnparsedLine] = field(default_factory=list)
    source_file: str = ""

    @property
    def parse_rate(self) -> float:
        total = len(self.rows) + len(self.unparsed)
        return len(self.rows) / total if total else 0.0

    def stats(self) -> dict:
        return {
            "parsed": len(self.rows),
            "unparsed": len(self.unparsed),
            "parse_rate": round(self.parse_rate, 4),
            "source_file": self.source_file,
        }


class SourceAdapter(Protocol):
    name: str

    def sniff(self, path: Path) -> bool:
        """Return True if this adapter recognizes the file."""
        ...

    def parse(self, path: Path, password: str | None = None) -> ParseResult:
        ...
