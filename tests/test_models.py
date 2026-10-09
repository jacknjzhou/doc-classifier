from doc_classifier.models import (
    RecognizedDoc, Section, Candidate, Evidence, MaterialHit, Classification, SubtypeResult,
)


def test_recognized_doc_sections_optional():
    d = RecognizedDoc(doc_id="d1", text="abc")
    assert d.sections is None and d.structured is None
    d2 = RecognizedDoc(doc_id="d2", text="ab", sections=[Section(index=0, text="a")])
    assert d2.sections[0].text == "a"


def test_classification_defaults():
    c = Classification(doc_id="d1")
    assert c.status == "unknown" and c.subtype is None
    assert c.category_path == [] and c.materials == [] and c.confidence == 0.0


def test_material_hit_degraded_flag():
    h = MaterialHit(material="invoice", display="发票", section=None, confidence=0.55, keyword="发票")
    assert h.degraded is False


def test_subtype_result_defaults():
    s = SubtypeResult()
    assert s.option is None and s.display is None and s.tie is False and s.hits == {}
