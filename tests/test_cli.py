import json
from pathlib import Path

from doc_classifier.cli import main

RULES_PATH = Path(__file__).resolve().parent.parent / "doc_classifier" / "rules.yaml"


def test_cli_roundtrip(tmp_path, rules, capsys):
    inp, out = tmp_path / "in.jsonl", tmp_path / "out.jsonl"
    docs = [
        {"doc_id": "c1", "text": "技术服务合同 甲方：阿里巴巴（中国）有限公司"},
        {"doc_id": "g1", "text": "###@@@"},
    ]
    inp.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in docs), encoding="utf-8")
    rc = main(["--rules", str(RULES_PATH), "--input", str(inp), "--output", str(out)])
    assert rc == 0
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["status"] == "classified" and first["category_path"][0] == "合同"
    assert json.loads(lines[1])["status"] in ("unknown", "review")  # review/unknown 样本落盘（R5 回流）

    captured = capsys.readouterr().out
    assert "规则命中率" in captured and "LLM调用率" in captured
