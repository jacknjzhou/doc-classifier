"""①c 子类型判定（design 4.3）：required 门控 + 权重计分 + 并列→不猜。"""

from __future__ import annotations

from .config import SubtypesSpec
from .models import MaterialHit, SubtypeResult

_TOLERANCE = 1e-9


def resolve_subtype(hits: dict[str, MaterialHit], subtypes: SubtypesSpec) -> SubtypeResult:
    """hits = 材料名 → 最高 MaterialHit（来自 ①b 检测）。

    - 候选资格：required 材料全命中（缺一即无资格）；
    - 计分 = |required∩hits| × weight_required + |optional∩hits| × weight_optional（权重取 option 配置）；
    - 唯一最高分 → 命中；最高分并列 → tie=True, option=None；无候选 → option=None, tie=False。
    """
    scores: dict[str, float] = {}
    for oname, opt in subtypes.options.items():
        req_hit = sum(1 for m in opt.required if m in hits)
        if req_hit < len(opt.required):
            continue
        opt_hit = sum(1 for m in opt.optional if m in hits)
        scores[oname] = req_hit * opt.weight_required + opt_hit * opt.weight_optional

    result = SubtypeResult(hits=hits)
    if not scores:
        return result  # 无候选（option=None, tie=False）→ pipeline 将最终 status 置 review

    max_s = max(scores.values())
    top = [n for n, s in scores.items() if abs(s - max_s) < _TOLERANCE]
    if len(top) > 1:
        result.tie = True
        return result
    result.option = top[0]
    result.display = subtypes.options[top[0]].display
    return result
