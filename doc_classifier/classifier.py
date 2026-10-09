"""⑤ 分类决策（design 4.3 钉死规则 1-6）：

- 输入 candidates 已按 (field, 归一化值) 分组（pipeline ④ 合并）；
- 每维度：best=组内最高 conf；best < threshold → 未通过；多组同分最高 → 并列（不猜）；
- 主维度 = **通过的维度中 priority 最小者**；
- 最终 status：完全无候选 → unknown；有候选但无维度通过 → review；
  任一有候选的维度低于阈值/并列 → review；否则 classified。
- 子类型层启用而 ①c 无命中/并列 → review（即使维度通过）。
- category_path = [doc_type.display] + [subtype.display?命中] + [各通过维度**原始**值, priority 升序]；
  review → [doc_type.display]；unknown → []。category_key = 主维度归一化值。
"""

from __future__ import annotations

from .config import DimensionRef, RulesConfig
from .models import (
    Candidate,
    Classification,
    DocTypeResult,
    Evidence,
    RecognizedDoc,
    SubtypeResult,
)
from .normalizers import normalize

_TOLERANCE = 1e-9

# 维度状态
PASS, BELOW, TIE, ABSENT = "pass", "below", "tie", "absent"


def _dim_state(cands: list[Candidate], threshold: float) -> tuple[str, Candidate | None]:
    """cands = 已合并的组代表（每组一个，value 为组内原始值代表）。"""
    if not cands:
        return ABSENT, None
    best = max(cands, key=lambda c: c.confidence)
    if any(abs(c.confidence - best.confidence) < _TOLERANCE for c in cands if c is not best):
        return TIE, best
    if best.confidence < threshold:
        return BELOW, best
    return PASS, best


def classify(
    doc: RecognizedDoc,
    doc_type_res: DocTypeResult,
    subtype_res: SubtypeResult,
    candidates: dict[str, list[Candidate]],
    rules: RulesConfig,
) -> Classification:
    result = Classification(doc_id=doc.doc_id)

    dt_spec = rules.document_types.get(doc_type_res.name) if doc_type_res.name else None
    if dt_spec is None:
        # ① 未判定（unknown）或 ① 层面 review（doc_type 并列，name=None）
        result.status = doc_type_res.status if doc_type_res.status in ("review", "unknown") else "review"
        result.doc_type = doc_type_res.name
        if result.status == "review" and doc_type_res.matched:
            # 配置顺序首个并列候选供展示（rules.yaml 口径）
            max_s = max(doc_type_res.matched.values())
            first = next(
                (n for n, s in doc_type_res.matched.items() if abs(s - max_s) < _TOLERANCE), None
            )
            if first and first in rules.document_types:
                result.category_path = [rules.document_types[first].display]
        result.confidence = doc_type_res.confidence
        return result

    result.doc_type = doc_type_res.name
    first_display = dt_spec.display
    result.category_path = [first_display]

    dims: list[DimensionRef] = sorted(dt_spec.dimensions, key=lambda d: d.priority)
    states: dict[str, tuple[str, Candidate | None]] = {}
    for ref in dims:
        dim = rules.dimensions[ref.use]
        states[ref.use] = _dim_state(candidates.get(ref.use, []), dim.threshold)

    any_cands = any(states[f][1] is not None for f in states)
    passed = [d.use for d in dims if states[d.use][0] == PASS]
    failed = [d.use for d in dims if states[d.use][0] in (BELOW, TIE)]
    subtype_blocked = dt_spec.subtypes is not None and subtype_res.option is None

    if not any_cands:
        result.status = "unknown"  # design 钉死 6：完全无候选 → unknown
    elif not passed or failed or subtype_blocked:
        result.status = "review"  # 有候选但无维度通过 / 低于阈值 / 并列 / 子类型未命中
    else:
        result.status = "classified"

    if result.status == "classified":
        for ref in dims:
            field = ref.use
            state, best = states[field]
            if state == PASS and best is not None:
                result.category_path.append(best.value)
                result.evidence.append(Evidence(source=best.source, value=best.value, span=best.span, confidence=best.confidence))
        if passed:
            # 主维度 = 通过的维度中 priority 最小者
            primary = min(passed, key=lambda f: next(d.priority for d in dims if d.use == f))
            best = states[primary][1]
            result.dimension = primary
            result.category_display = best.value
            result.category_key = normalize(best.value, primary, rules)
            result.confidence = best.confidence
        if subtype_res.option and subtype_res.display:
            result.subtype = subtype_res.option
            result.category_path.insert(1, subtype_res.display)
            result.materials = [m for m, hit in subtype_res.hits.items() if hit.confidence > 0]
        for m, hit in subtype_res.hits.items():  # 材料命中也是证据（可追溯）
            if hit.confidence > 0:
                result.evidence.append(Evidence(source="material", value=hit.keyword, span=None, confidence=hit.confidence))
    else:
        result.confidence = max((c.confidence for cs in candidates.values() for c in cs), default=0.0)
        if failed:  # review 时保留最高候选信息供复核展示（不进路径）
            f = failed[0]
            best = states[f][1]
            if best is not None:
                result.dimension = f
                result.category_display = best.value
                result.category_key = normalize(best.value, f, rules)
                result.evidence.append(Evidence(source=best.source, value=best.value, span=best.span, confidence=best.confidence))
        if subtype_res.hits:
            result.materials = [m for m, hit in subtype_res.hits.items() if hit.confidence > 0]

    return result
