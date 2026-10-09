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
_DEFAULT_PERSON_LABELS = ["姓名", "报销人", "请假人", "申请人", "联系人", "作者"]

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

        labels = (
            ctx.dimension.labels
            if (ctx.dimension is not None and ctx.dimension.labels)
            else _DEFAULT_PERSON_LABELS  # 内置默认（design 4.5）；rules.yaml 配置优先
        )
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


class ItemExtractor:
    """物品：标签邻接 0.9（品名/货物名称/物料）+ 数量×单位模式 0.7。"""

    name = "item"

    _UNIT_A = re.compile(r"([\u4e00-\u9fffA-Za-z0-9]{2,20}?)\s*\d{1,4}\s*(?:台|套|件|个|箱|盒)")
    _UNIT_B = re.compile(r"(?<!\d)\d{1,4}\s*(?:台|套|件|个|箱|盒)\s*([\u4e00-\u9fffA-Za-z0-9]{2,20})")
    _DEFAULT_LABELS = ["品名", "货物名称", "物料"]

    def extract(
        self,
        doc: RecognizedDoc,
        field: str,
        ctx: ExtractContext,
    ) -> list[Candidate]:
        best: dict[str, tuple[float, tuple[int, int]]] = {}

        def add(value: str, conf: float, span: tuple[int, int]) -> None:
            if value and value not in best or (value in best and conf > best[value][0]):
                best[value] = (conf, span)

        labels = (
            ctx.dimension.labels
            if (ctx.dimension is not None and ctx.dimension.labels)
            else self._DEFAULT_LABELS
        )
        for label in labels:
            for m in re.finditer(re.escape(label) + r"[：:]\s*" + _VALUE, doc.text):
                add(m.group(1), 0.9, (m.start(1), m.end(1)))

        for pat in (self._UNIT_A, self._UNIT_B):
            for m in pat.finditer(doc.text):
                add(m.group(1), 0.7, (m.start(1), m.end(1)))

        return [
            Candidate(value=v, field=field, confidence=conf, source="rule", span=span)
            for v, (conf, span) in best.items()
        ]


class DepartmentExtractor:
    """部门：标签邻接 0.9（部门/所在部门/发文单位/发文部门）+ 组织后缀模式 0.7。

    后缀命中串需含词表项或整体以后缀结尾；包含关系去重（"请财务部" 吞并 "财务部" 时保留短者）。
    """

    name = "department"

    _SUFFIX = re.compile(r"([\u4e00-\u9fff]{2,8}?(?:部|中心|科|组|处|办公室|委员会))")
    _DEFAULT_LABELS = ["部门", "所在部门", "发文单位", "发文部门"]
    _HONORIFICS = ("部", "中心", "科", "组", "处", "办公室", "委员会")

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

        labels = (
            ctx.dimension.labels
            if (ctx.dimension is not None and ctx.dimension.labels)
            else self._DEFAULT_LABELS
        )
        for label in labels:
            for m in re.finditer(re.escape(label) + r"[：:]\s*([\u4e00-\u9fff]{2,12})", doc.text):
                add(m.group(1), 0.9, (m.start(1), m.end(1)))

        for m in self._SUFFIX.finditer(doc.text):
            v = m.group(1)
            s, e = m.start(1), m.end(1)
            # 词表项在命中串内部 → 从词表项起点裁剪前缀（"请财务部" → "财务部"）
            cuts = [i for w in _DEPARTMENTS if (i := v.find(w)) >= 0]
            if cuts:
                cut = min(cuts)
                v, s, e = v[cut:], s + cut, e
            if not any(w in v for w in _DEPARTMENTS) and not v.endswith(self._HONORIFICS):
                continue  # 防"部分/部门感"类误报
            add(v, 0.7, (s, e))

        # 包含关系去重："财务部" ⊂ "请财务部" → 丢弃长串（同置信度下短者为真名概率更高）
        values = list(best)
        for v in values:
            if any(o != v and o in v for o in values):
                best.pop(v)

        return [
            Candidate(value=v, field=field, confidence=conf, source="rule", span=span)
            for v, (conf, span) in best.items()
        ]


class TopicExtractor:
    """会议主题：标签 0.9（会议主题/议题）+ 关于…的会议纪要 0.7 + 首行回退 0.5。"""

    name = "topic"

    _ABOUT = re.compile(r"关于(.{2,28}?)的会议纪要")
    _DEFAULT_LABELS = ["会议主题", "议题"]

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

        labels = (
            ctx.dimension.labels
            if (ctx.dimension is not None and ctx.dimension.labels)
            else self._DEFAULT_LABELS
        )
        for label in labels:
            for m in re.finditer(re.escape(label) + r"[：:]\s*([^。；;\n]{2,40})", doc.text):
                segs = m.group(1).split()
                cut = [i for i, s in enumerate(segs) if ("：" in s) or (":" in s)]
                if cut:
                    segs = segs[: min(cut)]  # 下一个字段标签 → 截止
                if segs:
                    add(" ".join(segs), 0.9, (m.start(1), m.start(1) + len(m.group(1))))

        for m in self._ABOUT.finditer(doc.text):
            add(m.group(1), 0.7, (m.start(1), m.end(1)))

        if not best:  # 回退：首行（2-30 字）
            scope = doc.sections[0].text if doc.sections else doc.text
            first = next((ln.strip() for ln in scope.splitlines() if ln.strip()), "")
            if 2 <= len(first) <= 30:
                add(first, 0.5, (scope.find(first), scope.find(first) + len(first)))

        return [
            Candidate(value=v, field=field, confidence=conf, source="rule", span=span)
            for v, (conf, span) in best.items()
        ]


register_extractor("party_a", PartyAExtractor())
register_extractor("person", PersonExtractor())
register_extractor("item", ItemExtractor())
register_extractor("department", DepartmentExtractor())
register_extractor("topic", TopicExtractor())
