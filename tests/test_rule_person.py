import pytest

from doc_classifier.extractors.base import ExtractContext
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.models import RecognizedDoc


@pytest.fixture(autouse=True)
def _setup(rules):
    from doc_classifier.extractors.rule import PersonExtractor

    return PersonExtractor


def _extract(doc, ctx):
    return get_extractor("person").extract(doc, "person_name", ctx)


def _ctx(rules):
    return ExtractContext(rules=rules)


def test_label_name(rules):
    doc = RecognizedDoc(doc_id="p1", text="姓名：张三 电话：13800000000")
    cands = _extract(doc, _ctx(rules))
    assert any(c.value == "张三" and c.confidence >= 0.9 for c in cands)


def test_label_reimburser_from_config(rules):  # labels 含 报销人（配置驱动）
    doc = RecognizedDoc(doc_id="p2", text="报销人：李四 部门：财务部")
    cands = _extract(doc, _ctx(rules))
    assert any(c.value == "李四" and c.confidence >= 0.9 for c in cands)


def test_honorific(rules):
    doc = RecognizedDoc(doc_id="p3", text="李四经理负责本次对接")
    cands = _extract(doc, _ctx(rules))
    assert any(c.value == "李四" and 0.7 <= c.confidence <= 0.9 for c in cands)


def test_bare_2char_below_threshold(rules):  # design R10：无邻接 2 字名不通过
    doc = RecognizedDoc(doc_id="p4", text="他跟李四喝了杯酒")
    cands = _extract(doc, _ctx(rules))
    assert all(c.confidence < 0.6 for c in cands)
