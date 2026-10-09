from doc_classifier.extractors.base import ExtractContext
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.models import RecognizedDoc


def _extract(doc, rules):
    return get_extractor("item").extract(doc, "item_name", ExtractContext(rules=rules))


def test_item_label(rules):
    doc = RecognizedDoc(doc_id="i1", text="品名：笔记本电脑 数量：2 台 单价：5000")
    cands = _extract(doc, rules)
    assert any(c.value == "笔记本电脑" and c.confidence >= 0.9 for c in cands)


def test_item_unit_pattern(rules):
    doc = RecognizedDoc(doc_id="i2", text="本次采购 联想笔记本电脑 2台 及 打印纸 10 箱")
    cands = _extract(doc, rules)
    assert any(c.value == "联想笔记本电脑" for c in cands)
    assert any(c.value == "打印纸" for c in cands)
