from doc_classifier.extractors.base import ExtractContext
from doc_classifier.extractors.material import KeywordMaterialDetector
from doc_classifier.extractors.registry import get_material_detector
from doc_classifier.models import RecognizedDoc, Section


def _package_doc(with_sections=True):
    secs = [
        Section(index=0, text="审批单 报销人：张三 审批通过"),
        Section(index=1, text="增值税普通发票 发票号码：1 价税合计：100"),
        Section(index=2, text="行程单 登机牌 北京-上海"),
        Section(index=3, text="住宿 酒店 房费 300"),
    ]
    return RecognizedDoc(
        doc_id="pkg",
        text=" ".join(s.text for s in secs),
        sections=secs if with_sections else None,
    )


def test_section_detection(rules):
    det = get_material_detector("keyword")
    hits = {}
    for name, spec in rules.document_types["reimbursement"].subtypes.materials.items():
        for h in det.detect(_package_doc(), spec, ExtractContext(rules=rules, degraded=False)):
            hits[h.material] = h
    assert set(hits) == {"invoice", "itinerary", "hotel", "approval"}
    assert all(not h.degraded for h in hits.values())


def test_fulltext_degraded(rules):  # sections=None → 全文检测 + degraded
    det = get_material_detector("keyword")
    hits = []
    for name, spec in rules.document_types["reimbursement"].subtypes.materials.items():
        hits += det.detect(_package_doc(with_sections=False), spec, ExtractContext(rules=rules, degraded=True))
    mats = {h.material for h in hits}
    assert {"invoice", "itinerary", "hotel", "approval"} <= mats
    assert all(h.degraded and h.section is None for h in hits)


def test_no_keyword_no_hit(rules):
    det = get_material_detector("keyword")
    doc = RecognizedDoc(doc_id="plain", text="今天天气不错")
    assert (
        det.detect(
            doc,
            rules.document_types["reimbursement"].subtypes.materials["invoice"],
            ExtractContext(rules=rules),
        )
        == []
    )
