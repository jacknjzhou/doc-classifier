from doc_classifier.extractors.base import ExtractContext
from doc_classifier.extractors.registry import get_extractor
from doc_classifier.models import RecognizedDoc


def _extract(doc, rules):
    return get_extractor("topic").extract(doc, "meeting_name", ExtractContext(rules=rules))


def test_topic_label(rules):
    doc = RecognizedDoc(doc_id="m1", text="会议主题：Q4 营销方案评审会 参会人员：…")
    assert any(c.value == "Q4 营销方案评审会" for c in _extract(doc, rules))


def test_topic_about_pattern(rules):
    doc = RecognizedDoc(doc_id="m2", text="关于年度审计的会议纪要")
    assert any(c.value == "年度审计" for c in _extract(doc, rules))
