from doc_classifier.extractors.base import ExtractContext
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.models import RecognizedDoc


def _extract(doc, rules):
    return get_extractor("invoice_title").extract(doc, "invoice_title", ExtractContext(rules=rules))


def test_buyer_with_taxid_boost(rules):
    doc = RecognizedDoc(doc_id="v1", text="购方名称：XX信息技术有限公司 税号：91330106MA2B9C3D4E")
    cands = _extract(doc, rules)
    hit = [c for c in cands if c.value == "XX信息技术有限公司"]
    assert hit and hit[0].confidence >= 1.0 - 1e-9  # 税号邻位 +0.2，上限 1.0


def test_buyer_without_taxid(rules):
    doc = RecognizedDoc(doc_id="v2", text="购方名称：YY科技有限公司")
    cands = _extract(doc, rules)
    hit = [c for c in cands if c.value == "YY科技有限公司"]
    assert hit and 0.85 <= hit[0].confidence <= 0.95
