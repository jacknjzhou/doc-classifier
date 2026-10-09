"""⑤ 分类决策（design 4.3 钉死规则）：

- 每个维度：best = 最高置信候选；best < threshold → 未通过；并列最高 → 不猜；无候选 → 缺席。
- 最终状态：doc_type 未定 → unknown；主维度未通过（低于/并列/缺席）→ review；
  任一次维度低于阈值或并列 → review（缺席次维度不影响）；子类型层启用而 ①c 无命中/并列 → review。
- category_path = [doc_type.display] + [subtype.display?命中] + [各通过维度**原始**值, priority 升序]；
  review → [doc_type.display]；unknown → []。category_key = 主维度归一化值。
"""

from __future__ import annotations

from .config import DimensionRef, RulesConfig
from .models import Candidate, Classification, DocTypeResult, RecognizedDoc, SubtypeResult
from .normalizers import normalize

_TOLERANCE = 1e-9

# 维度状态
PASS, BELOW, TIE, ABSENT = "pass", "below", "tie", "absent"


def _dim_state(field: str, cands: list[Candidate], threshold: float) -> tuple[str, Candidate | None]:
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
        status = doc_type_res.status if doc_type_res.status in ("review", "unknown") else "review"
        result.status = status
        result.doc_type = doc_type_res.name
        result.category_path = []
        result.confidence = doc_type_res.confidence
        return result

    result.doc_type = doc_type_res.name
    first_display = dt_spec.display
    result.category_path = [first_display]

    dims: list[DimensionRef] = sorted(dt_spec.dimensions, key=lambda d: d.priority)
    states: dict[str, tuple[str, Candidate | None]] = {}
    for ref in dims:
        dim = rules.dimensions[ref.use]
        states[ref.use] = _dim_state(ref.use, candidates.get(ref.use, []), dim.threshold)

    primary = dims[0].use if dims else None
    primary_state = states.get(primary, (ABSENT, None)) if primary else (ABSENT, None)

    # 子类型层：启用而未命中（无候选/并列）→ 整篇 review（design 4.3 钉死）
    subtype_blocked = dt_spec.subtypes is not None and subtype_res.option is None

    if primary_state[0] in (BELOW, TIE, ABSENT) or subtype_blocked:
        result.status = "review"
        result.confidence = max((c.confidence for cs in candidates.values() for c in cs), default=0.0)
        result.category_path = [first_display]
    elif any(states[d.use][0] in (BELOW, TIE) for d in dims[1:]):
        result.status = "review"
        result.confidence = max((c.confidence for cs in candidates.values() for c in cs), default=0.0)
        result.category_path = [first_display]
    else:
        result.status = "classified"

    # 仅 classified 才落维度值/证据（review 路径 = [doc_type.display]，design 4.3 钉死）
    if result.status == "classified":
        for ref in dims:
            field = ref.use
            state, best = states[field]
            if state == PASS and best is not None:
                result.category_path.append(best.value)
                result.evidence.append(_evidence(best))
            if field == primary and best is not None and state == PASS:
                result.dimension = field
                result.category_display = best.value
                result.category_key = normalize(best.value, field, rules)
                result.confidence = max(result.confidence, best.confidence)
        if subtype_res.option and subtype_res.display:
            result.subtype = subtype_res.option
            result.category_path.insert(1, subtype_res.display)
            result.materials = [m for m, hit in subtype_res.hits.items() if hit.confidence > 0]
    else:  # review：主维度信息保留（供复核展示），不进路径
        if primary and states.get(primary, (None, None))[1] is not None:
            best = states[primary][1]
            result.dimension = primary
            result.category_display = best.value
            result.category_key = normalize(best.value, primary, rules)
            result.evidence.append(_evidence(best))
        if subtype_res.hits:
            result.materials = [m for m, hit in subtype_res.hits.items() if hit.confidence > 0]

    return result


def _evidence(c: Candidate):
    from .models import Evidence

    return Evidence(source=c.source, value=c.value, span=c.span, confidence=c.confidence)
