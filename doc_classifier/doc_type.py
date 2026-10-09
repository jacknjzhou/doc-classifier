"""① 文档类型判定（design 3.2/4.4）：关键词计分 + 标题加权 + 并列→review。

判定域（防报销包内发票页"抢跑"，design R7）：
- 有分节 → 第一个分节的文本 + 第一个分节的标题（标题命中关键词额外 +1）
- 无分节（sections=None）→ 全文
"""

from __future__ import annotations

from .config import DocTypeSpec, RulesConfig
from .models import DocTypeResult, RecognizedDoc, Section

_KEYWORD_W = 1.0
_TITLE_W = 1.0
_MIN_SCORE = 1.0
_TOLERANCE = 1e-9


def _scope_and_title(doc: RecognizedDoc) -> tuple[str, str]:
    if doc.sections:
        first: Section = doc.sections[0]
        return first.text, first.title or ""
    return doc.text, ""


def _score(dt: DocTypeSpec, scope: str, title: str) -> float:
    score = 0.0
    for kw in dt.keywords:
        if kw in scope:  # distinct：每个关键词至多计一次
            score += _KEYWORD_W
            if title and kw in title:
                score += _TITLE_W
    return score


def detect_doc_type(doc: RecognizedDoc, rules: RulesConfig) -> DocTypeResult:
    scope, title = _scope_and_title(doc)
    matched = {
        dt.name: _score(dt, scope, title) for dt in rules.document_types.values() if _score(dt, scope, title) > 0
    }
    if not matched:
        return DocTypeResult(name=None, confidence=0.0, matched=matched, status="unknown")

    max_s = max(matched.values())
    top = [n for n, s in matched.items() if abs(s - max_s) < _TOLERANCE]
    if len(top) == 1 and max_s >= _MIN_SCORE:
        return DocTypeResult(
            name=top[0],
            confidence=min(1.0, max_s / 3.0),
            matched=matched,
            status="classified",
        )
    # 并列（或最高分未达阈值且存在竞争）→ review，绝不猜
    return DocTypeResult(name=None, confidence=min(1.0, max_s / 3.0), matched=matched, status="review")
