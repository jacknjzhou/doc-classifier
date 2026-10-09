"""L1 规则抽取器（正则/标签/词表；标签集来自 DimensionSpec.labels 配置）。"""

from __future__ import annotations

import re
from pathlib import Path

from ..models import Candidate, RecognizedDoc
from .base import ExtractContext
from .registry import register_extractor

# 标签后取值：捕获到行内分隔符为止
_VALUE = r"([^\s，。；;：:]{2,40})"

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_words(filename: str) -> frozenset[str]:
    p = _DATA_DIR / filename
    return frozenset(line.strip() for line in p.read_text(encoding="utf-8").splitlines() if line.strip())


_SURNAMES = _load_words("surnames.txt")
_DEPARTMENTS = _load_words("departments.txt") if (_DATA_DIR / "departments.txt").exists() else frozenset()

_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_HONORIFIC = re.compile(r"(?<![\u4e00-\u9fff])([\u4e00-\u9fff]{2,3})(?=\s?(?:先生|女士|同志|经理|老师|总监))")


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


class PersonExtractor:
    """人名三策略：标签邻接 0.9 / 称谓邻接 0.8 / 姓氏表（独立 run）3 字 0.6、2 字 0.4。

    防误报（design R10）：嵌入更长中文 run 的名字不产出，交由 LLM 兕底。
    """

    name = "person"

    def extract(
        self,
        doc: RecognizedDoc,
        field: str,
        ctx: ExtractContext,
    ) -> list[Candidate]:
        best: dict[str, tuple[float, tuple[int, int]]] = {}

        def add(value: str, conf: float, span: tuple[int, int]) -> None:
            if value not in best or conf > best[value][0]:
                best[value] = (conf, span)

        labels = ctx.dimension.labels if ctx.dimension else []
        for label in labels:  # 策略 1：标签邻接
            pat = re.compile(re.escape(label) + r"[：:]\s*(?:([\u4e00-\u9fff]{2,10}))")
            for m in pat.finditer(doc.text):
                add(m.group(1), 0.9, (m.start(1), m.end(1)))

        for m in _HONORIFIC.finditer(doc.text):  # 策略 2：称谓邻接
            add(m.group(1), 0.8, (m.start(1), m.end(1)))

        for m in _CJK_RUN.finditer(doc.text):  # 策略 3：姓氏表（仅独立 2-3 字 run）
            run = m.group(0)
            if len(run) not in (2, 3):
                continue  # 嵌入长 run 的名字不产出
            if run[0] in _SURNAMES:
                add(run, 0.6 if len(run) == 3 else 0.4, (m.start(), m.end()))

        return [
            Candidate(value=v, field=field, confidence=conf, source="rule", span=span)
            for v, (conf, span) in best.items()
        ]


register_extractor("party_a", PartyAExtractor())
register_extractor("person", PersonExtractor())
