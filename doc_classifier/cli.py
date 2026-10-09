"""CLI 入口（design 4.8）：JSONL 进 → 逐篇 classify_doc → JSONL 出 + stdout summary。

用法：
    python -m doc_classifier --rules rules.yaml --input docs.jsonl --output out.jsonl [--llm auto|on|off]
输入行 = RecognizedDoc（doc_id/text/sections?/structured?/source?）；
输出行 = Classification 序列化（status/category_path/materials/evidence…）；review/unknown 同样落盘（R5 回流）。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_rules
from .extractors.llm import LLMExtractor
from .models import Classification, RecognizedDoc, Section
from .pipeline import classify_docs

_PKG_RULES = Path(__file__).resolve().parent / "rules.yaml"


def _to_doc(d: dict) -> RecognizedDoc:
    raw_sections = d.get("sections") or None
    sections = None
    if raw_sections:
        sections = [
            Section(index=s.get("index", i), text=s.get("text", ""), title=s.get("title"))
            for i, s in enumerate(raw_sections)
        ]
    return RecognizedDoc(
        doc_id=d.get("doc_id", ""),
        text=d.get("text", ""),
        sections=sections,
        structured=d.get("structured"),
        source=d.get("source", ""),
    )


def _to_dict(c: Classification) -> dict:
    return {
        "doc_id": c.doc_id,
        "status": c.status,
        "doc_type": c.doc_type,
        "subtype": c.subtype,
        "dimension": c.dimension,
        "category_key": c.category_key,
        "category_display": c.category_display,
        "category_path": c.category_path,
        "materials": c.materials,
        "confidence": c.confidence,
        "evidence": [
            {
                "source": e.source,
                "value": e.value,
                "span": list(e.span) if e.span else None,
                "confidence": e.confidence,
            }
            for e in c.evidence
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="doc_classifier", description="维度涌现式文档分类引擎")
    parser.add_argument("--rules", default=str(_PKG_RULES), help="rules.yaml 路径（默认包内）")
    parser.add_argument("--input", required=True, help="输入 JSONL（每行一篇文档）")
    parser.add_argument("--output", required=True, help="输出 JSONL（每行一个 Classification）")
    parser.add_argument("--llm", choices=["auto", "on", "off"], default="auto", help="LLM 开关覆盖（默认按配置）")
    args = parser.parse_args(argv)

    rules = load_rules(args.rules)
    if args.llm == "on":
        rules.llm.enabled = True
    elif args.llm == "off":
        rules.llm.enabled = False
    llm = LLMExtractor() if rules.llm.enabled else None

    docs = [
        _to_doc(json.loads(line))
        for line in Path(args.input).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    results, summary = classify_docs(docs, rules, llm=llm)

    Path(args.output).write_text(
        "\n".join(json.dumps(_to_dict(c), ensure_ascii=False) for c in results) + ("\n" if results else ""),
        encoding="utf-8",
    )

    print(
        f"共 {summary.total} 篇 | classified {summary.classified} | review {summary.review}"
        f" | unknown {summary.unknown} | 规则命中率 {summary.rule_hit_rate:.0%}"
        f" | LLM调用率 {summary.llm_rate:.0%}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
