"""Adapter registry — sniff a file and hand back the right adapter."""
from __future__ import annotations

from pathlib import Path

from app.pipeline.adapters.base import ParseResult, SourceAdapter
from app.pipeline.adapters.phonepe_csv import PhonePeCSVAdapter
from app.pipeline.adapters.phonepe_pdf import PhonePePDFAdapter

ADAPTERS: list[SourceAdapter] = [PhonePeCSVAdapter(), PhonePePDFAdapter()]


def pick_adapter(path: Path) -> SourceAdapter | None:
    for adapter in ADAPTERS:
        if adapter.sniff(path):
            return adapter
    return None


def parse_file(path: Path, password: str | None = None) -> ParseResult:
    adapter = pick_adapter(path)
    if adapter is None:
        raise ValueError(f"No adapter recognizes {path.name}")
    return adapter.parse(path, password)
