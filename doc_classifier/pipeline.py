"""④→⑥ 流水线编排（design 4.1）：doc_type → 材料 → 子类型 → 维度抽取（规则+LLM 兜底）→ 合并 → 分类决策。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from . import normalizers
from .classifier import classify
from .config import RulesConfig
from .doc_type import detect_doc_type
from .extractors.base import ExtractContext
from .extractors.llm import LLMExtractor
from .extractors.registry import get_extractor, get_material_detector
from .models import Candidate, Classification, RecognizedDoc, SubtypeResult
from .subtype import resolve_subtype

log = logging.getLogger(__name__)


@dataclass
class Summary:
    """⑥ 批次指标（design 4.7）。"""

    total: int = 0
    classified: int = 0
    review: int = 0
    unknown: int = 0
    llm_docs: int = 0  # 实际触发 ≥1 次 LLM 调用的文档数
    llm_calls: int = 0
    llm_failed: int = 0

    @property
    def llm_rate(self) -> float:
        return self.llm_docs / self.total if self.total else 0.0

    @property
    def rule_hit_rate(self) -> float:
        return 1.0 - self.llm_rate


def _section_spans(doc: RecognizedDoc) -> list[tuple[int, int]]:
    """各分节在全文中的 (start, end) 区间。"""
    spans: list[tuple[int, int]] = []
    off = 0
    for s in doc.sections or []:
        idx = doc.text.find(s.text, max(0, off - 1))
        start = idx if idx >= 0 else off
        spans.append((start, start + len(s.text)))
        off = start + len(s.text) + 1  # 拼接分隔符（\n 或 空格，取保守估计）
    return spans


def _merge_candidates(rule_cands: list[Candidate], llm_cands: list[Candidate], field: str, rules: RulesConfig) -> list[Candidate]:
    """候选合并（design 4.3 钉死 1-2）：按 (field, 归一化值) 分组，组内 conf=max。"""
    groups: dict[str, Candidate] = {}
    for c in [*rule_cands, *llm_cands]:
        norm = normalizers.normalize(c.value, field, rules)
        key = norm or c.value
        prev = groups.get(key)
        if prev is None or c.confidence > prev.confidence:
            groups[key] = Candidate(
                value=c.value, field=c.field, confidence=c.confidence, source=c.source, span=c.span
            )
    return list(groups.values())


def _section_index_of(spans: list[tuple[int, int]], pos: int) -> int | None:
    for i, (s, e) in enumerate(spans):
        if s <= pos < e:
            return i
    return None


def classify_doc(doc: RecognizedDoc, rules: RulesConfig, llm: LLMExtractor | None = None) -> Classification:
    degraded = doc.sections is None
    base_ctx = ExtractContext(rules=rules, degraded=degraded)

    # ① 文档类型
    dt_res = detect_doc_type(doc, rules)
    dt = rules.document_types.get(dt_res.name) if dt_res.name else None
    if dt is None:
        return classify(doc, dt_res, SubtypeResult(), {}, rules)

    # ①b 材料检测（全分节；无分节 → 全文降级）
    hits: dict = {}
    if dt.subtypes is not None and dt_res.status == "classified":
        for spec in dt.subtypes.materials.values():
            detector = get_material_detector(spec.detector or "keyword")
            for h in detector.detect(doc, spec, base_ctx):
                if h.material not in hits or h.confidence > hits[h.material].confidence:
                    hits[h.material] = h
        # ①c 子类型
        subtype_res = resolve_subtype(hits, dt.subtypes)
    else:
        subtype_res = SubtypeResult()

    # ② 维度选择：子类型命中且配置了维度覆盖 → 用覆盖
    dims = sorted(dt.dimensions, key=lambda d: d.priority)
    if subtype_res.option and dt.subtypes is not None:
        override = dt.subtypes.options[subtype_res.option].dimensions
        if override:
            dims = sorted(override, key=lambda d: d.priority)

    # ③ 规则抽取（逐维度）
    cands: dict[str, list[Candidate]] = {}
    for ref in dims:
        dim = rules.dimensions[ref.use]
        ctx = ExtractContext(rules=rules, dimension=dim, degraded=degraded)
        cands[ref.use] = get_extractor(dim.extractor).extract(doc, ref.use, ctx)

    # LLM 兜底（design 4.3 钉死）：主维度（priority 最小）规则后未达阈值才调用
    primary = dims[0].use if dims else None
    if primary and llm is not None and llm.enabled(base_ctx):
        pdim = rules.dimensions[primary]
        pbest = max((c.confidence for c in cands[primary]), default=0.0)
        if pbest < pdim.threshold:
            fields = [
                ref.use
                for ref in dims
                if rules.dimensions[ref.use].llm_fallback
                and max((c.confidence for c in cands[ref.use]), default=0.0) < rules.dimensions[ref.use].threshold
            ]
            if fields:
                # 送文焦点 = 含规则命中的分节（全未命中时 llm 内部送第一个分节）
                spans = _section_spans(doc) if doc.sections else []
                focus: list[int] = []
                for ref in dims:
                    for c in cands[ref.use]:
                        if c.span is not None and spans:
                            si = _section_index_of(spans, c.span[0])
                            if si is not None and si not in focus:
                                focus.append(si)
                llm_out = llm.extract_fields(doc, fields, base_ctx, focus=focus or None)
                for f, cs in llm_out.items():
                    cands[f] = _merge_candidates(cands.get(f, []), cs, f, rules)

    # ④⑤ 合并 + 分类决策
    merged = {f: _merge_candidates(cs, [], f, rules) for f, cs in cands.items()}
    return classify(doc, dt_res, subtype_res, merged, rules)


def classify_docs(
    docs: list[RecognizedDoc], rules: RulesConfig, llm: LLMExtractor | None = None
) -> tuple[list[Classification], Summary]:
    summary = Summary(total=len(docs))
    results = []
    for doc in docs:
        before = llm.calls if llm is not None else 0
        c = classify_doc(doc, rules, llm=llm)
        results.append(c)
        summary.classified += c.status == "classified"
        summary.review += c.status == "review"
        summary.unknown += c.status == "unknown"
        if llm is not None:
            if llm.calls > before:
                summary.llm_docs += 1  # 逐文档计数（串行处理下精确）
            summary.llm_calls = llm.calls
            summary.llm_failed = llm.failed
    return results, summary
