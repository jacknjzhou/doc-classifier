from doc_classifier.extractors.base import ExtractContext
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.models import RecognizedDoc


def _extract(doc, rules):
    return get_extractor("department").extract(doc, "department_name", ExtractContext(rules=rules))


def test_label(rules):
    doc = RecognizedDoc(doc_id="n1", text="发文单位：人力资源部 兹定于周五开会")
    assert any(c.value == "人力资源部" and c.confidence >= 0.9 for c in _extract(doc, rules))


def test_suffix_pattern(rules):
    doc = RecognizedDoc(doc_id="n2", text="请财务部于本周五前提交报表")
    assert any(c.value == "财务部" for c in _extract(doc, rules))


def test_center_variant(rules):
    doc = RecognizedDoc(doc_id="n3", text="研发中心全体同事请注意")
    assert any(c.value == "研发中心" for c in _extract(doc, rules))
