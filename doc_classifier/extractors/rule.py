"""L1 规则抽取器（正则/标签/词表；标签集来自 DimensionSpec.labels 配置）。"""

from __future__ import annotations

import re

from ..models import Candidate, RecognizedDoc
from .base import ExtractContext
from .registry import register_extractor

# 标签后取值：捕获到行内分隔符为止
_VALUE = r"([^\s，。；;：:]{2,40})"


class PartyAExtractor:
    """甲方名称（标签：甲方 / 甲方名称，可配置）。"""

    name = "party_a"

    def extract(
        self,
        doc: RecognizedDoc,
        field: str,
        ctx: ExtractContext,
    ) -> list[Candidate]:
        labels = ctx.dimension.labels if ctx.dimension else ["甲方", "甲方名称"]
        out: list[Candidate] = []
        for label in labels:
            pat = re.compile(re.escape(label) + r"[：:]\s*" + _VALUE)
            for m in pat.finditer(doc.text):
                out.append(
                    Candidate(
                        value=m.group(1),
                        field=field,
                        confidence=0.9,
                        source="rule",
                        span=(m.start(1), m.end(1)),
                    )
                )
        return out


register_extractor("party_a", PartyAExtractor())
