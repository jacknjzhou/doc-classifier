"""①b 材料检测器（design 4.3）：通用关键词材料检测，材料定义完全来自配置。

- 检测单元 = doc.sections（每分节一条）；sections is None → 全文一条，degraded=ctx.degraded。
- 单材料单单元：每个 distinct 关键词命中 +0.1（基础 0.7；degraded 基础 0.55；上限 0.9）。
- 每材料至多产出一条 MaterialHit（跨单元取最高 conf，section 取首个命中分节）。
- 引擎不硬编码材料名；`detector: <注册名>` 自定义检测器实现同一 Protocol。
"""

from __future__ import annotations

from typing import Any

from ..models import MaterialHit, RecognizedDoc
from .base import ExtractContext
from .registry import register_material_detector

_BASE = 0.7
_DEGRADED_BASE = 0.55
_STEP = 0.1
_CAP = 0.9


class KeywordMaterialDetector:
    name = "keyword"

    def detect(
        self,
        doc: RecognizedDoc,
        material: Any,  # MaterialSpec（config 模型；避免循环导入）
        ctx: ExtractContext,
    ) -> list[MaterialHit]:
        name = getattr(material, "name", "")
        display = getattr(material, "display", "")
        keywords = list(getattr(material, "keywords", []))
        if not keywords:
            return []

        degraded = ctx.degraded and not doc.sections
        if doc.sections:
            units = [(s.index if s.index is not None else i, s.text) for i, s in enumerate(doc.sections)]
        else:
            units = [(None, doc.text)]

        best: MaterialHit | None = None
        for idx, text in units:
            hit_kws = [kw for kw in keywords if kw in text]
            if not hit_kws:
                continue
            base = _DEGRADED_BASE if degraded else _BASE
            conf = min(_CAP, base + _STEP * len(hit_kws))
            hit = MaterialHit(
                material=name,
                display=display,
                section=None if idx is None else idx,
                confidence=conf,
                keyword=hit_kws[0],
                degraded=degraded,
            )
            if best is None or conf > best.confidence:
                best = hit
        return [best] if best else []


register_material_detector("keyword", KeywordMaterialDetector())
