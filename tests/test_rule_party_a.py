import pytest

from doc_classifier.extractors.base import ExtractContext
from doc_classifier.extractors.registry import get_extractor, register_extractor
from doc_classifier.extractors.rule import PartyAExtractor
from doc_classifier.models import RecognizedDoc


@pytest.fixture(autouse=True)
def _reg():
    register_extractor("party_a", PartyAExtractor())


def _ctx(rules):
    return ExtractContext(rules=rules)


def test_party_a_label(rules):
    doc = RecognizedDoc(doc_id="c1", text="甲方：阿里巴巴（中国）有限公司 乙方：某软件公司")
    cands = get_extractor("party_a").extract(doc, "party_a_name", _ctx(rules))
    hit = [c for c in cands if c.value == "阿里巴巴（中国）有限公司"]
    assert hit and hit[0].confidence >= 0.9
    assert doc.text[hit[0].span[0] : hit[0].span[1]] == hit[0].value  # span 可回溯


def test_party_a_name_variant(rules):
    doc = RecognizedDoc(doc_id="c2", text="甲方名称：杭州某某科技有限公司")
    cands = get_extractor("party_a").extract(doc, "party_a_name", _ctx(rules))
    assert any(c.value == "杭州某某科技有限公司" for c in cands)


def test_party_a_halfwidth_colon(rules):
    doc = RecognizedDoc(doc_id="c3", text="甲方: 北京字节网络技术有限公司")
    cands = get_extractor("party_a").extract(doc, "party_a_name", _ctx(rules))
    assert any(c.value == "北京字节网络技术有限公司" for c in cands)
