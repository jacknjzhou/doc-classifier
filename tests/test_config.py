import pytest
from pydantic import ValidationError
from doc_classifier.config import load_rules

GOOD = """
version: "1.3"
llm: { enabled: false }
dimensions:
  person_name: { extractor: person, normalize: person, labels: [姓名] }
document_types:
  resume:
    display: 简历
    detect: { keywords: [简历, 求职], min_score: 1 }
    dimensions: [{ use: person_name, priority: 1 }]
    subtypes:
      materials: { note: { display: 备注, keywords: [备注] } }
      options: { memo: { display: 备注报销, required: [note] } }
"""


def _write(tmp_path, text):
    p = tmp_path / "r.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_load_valid(tmp_path):
    rules = load_rules(_write(tmp_path, GOOD))
    assert rules.llm.enabled is False  # 主开关默认关闭
    assert rules.dimensions["person_name"].labels == ["姓名"]
    assert rules.document_types["resume"].subtypes.options["memo"].required == ["note"]


def test_undefined_dimension_ref(tmp_path):  # use 引用未定义维度
    bad = GOOD.replace("use: person_name", "use: ghost")
    with pytest.raises(ValidationError, match="ghost"):
        load_rules(_write(tmp_path, bad))


def test_option_undefined_material(tmp_path):  # required 引用未定义材料
    bad = GOOD.replace("required: [note]", "required: [note, ghost]")
    with pytest.raises(ValidationError, match="ghost"):
        load_rules(_write(tmp_path, bad))


def test_unregistered_detector(tmp_path):  # detector 未注册
    bad = GOOD.replace("keywords: [备注]", "keywords: [备注], detector: nope")
    with pytest.raises(ValidationError, match="nope"):
        load_rules(_write(tmp_path, bad))
