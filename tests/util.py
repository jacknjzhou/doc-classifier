"""测试共享工具。"""

from __future__ import annotations

import json
from pathlib import Path

from doc_classifier.models import RecognizedDoc, Section

FIX = Path(__file__).parent / "fixtures"


def _load(path: str) -> RecognizedDoc:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = d.get("sections") or None
    sections = (
        [Section(index=s.get("index", i), text=s.get("text", ""), title=s.get("title")) for i, s in enumerate(raw)]
        if raw
        else None
    )
    return RecognizedDoc(
        doc_id=d.get("doc_id", ""),
        text=d.get("text", ""),
        sections=sections,
        structured=d.get("structured"),
        source=d.get("source", ""),
    )
