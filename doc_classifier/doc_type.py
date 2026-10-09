"""① 文档类型判定（design 3.2/4.4）：关键词计分 + 标题加权 + 并列→review。

判定域（防报销包内发票页"抢跑"，design R7）：
- 有分节 → 第一个分节的文本 + 第一个分节的标题（标题命中关键词额外 +1）
- 无分节（sections=None）→ 全文
状态：唯一达标且最高 → classified；并列最高 → review；无达标候选 → unknown。
"""

from __future__ import annotations

from .config import DocTypeSpec, RulesConfig
from .models import DocTypeResult, RecognizedDoc, Section

_KEYWORD_W = 1.0
_TITLE_W = 1.0
_TOLERANCE = 1e-9


def _scope_and_title(doc: RecognizedDoc) -> tuple[str, str]:
    if doc.sections:
        first: Section = doc.sections[0]
        return first.text, first.title or ""
    return doc.text, ""


def _score(dt: DocTypeSpec, scope: str, title: str) -> float:
    score = 0.0
    for kw in dt.detect.keywords:
        if kw in scope:  # distinct：每个关键词至多计一次
            score += _KEYWORD_W
            if title and kw in title:
                score += _TITLE_W
    return score


def detect_doc_type(doc: RecognizedDoc, rules: RulesConfig) -> DocTypeResult:
    scope, title = _scope_and_title(doc)
    matched = {
        name: s for name, dt in rules.document_types.items() if (s := _score(dt, scope, title)) > 0
    }
    if not matched:
        return DocTypeResult(name=None, confidence=0.0, matched=matched, status="unknown")

    max_s = max(matched.values())
    top = [n for n, s in matched.items() if abs(s - max_s) < _TOLERANCE]
    conf = min(1.0, max_s / 3.0)
    if len(top) == 1 and max_s >= rules.document_types[top[0]].detect.min_score:
        return DocTypeResult(name=top[0], confidence=conf, matched=matched, status="classified")
    if len(top) > 1:
        return DocTypeResult(name=None, confidence=conf, matched=matched, status="review")
    # 最高分未达自身 min_score：存在其他达标候选 → review；否则 unknown
    has_valid = any(s >= rules.document_types[n].detect.min_score for n, s in matched.items())
    return DocTypeResult(name=None, confidence=conf, matched=matched, status="review" if has_valid else "unknown")
