from doc_classifier.classifier import classify
from doc_classifier.models import (
    Candidate,
    DocTypeResult,
    MaterialHit,
    RecognizedDoc,
    SubtypeResult,
)


def _cand(field, value, conf, source="rule"):
    return Candidate(value=value, field=field, confidence=conf, source=source, span=(0, len(value)))


def _dt(name="contract", status="classified"):
    return DocTypeResult(name=name, confidence=1.0, matched={name: 3.0}, status=status)


def test_primary_pass(rules):
    doc = RecognizedDoc(doc_id="c1", text="甲方：阿里巴巴（中国）有限公司")
    cands = {"party_a_name": [_cand("party_a_name", "阿里巴巴（中国）有限公司", 0.9)], "person_name": []}
    res = classify(doc, _dt(), SubtypeResult(), cands, rules)
    assert res.status == "classified" and res.doc_type == "contract"
    assert res.category_path == ["合同", "阿里巴巴（中国）有限公司"]
    assert res.category_key == "阿里巴巴"  # 归一化
    assert res.dimension == "party_a_name"


def test_secondary_below_threshold(rules):
    doc = RecognizedDoc(doc_id="c2", text="甲方：A 公司 联系人：李四")
    cands = {
        "party_a_name": [_cand("party_a_name", "A 公司", 0.9)],
        "person_name": [_cand("person_name", "李四", 0.4)],
    }
    res = classify(doc, _dt(), SubtypeResult(), cands, rules)
    assert res.status == "review" and res.category_path == ["合同"]


def test_llm_fill(rules):
    doc = RecognizedDoc(doc_id="r1", text="求职意向：后端开发")
    cands = {"person_name": [
        _cand("person_name", "张三", 0.55),
        _cand("person_name", "张三", 0.75, source="llm"),
    ]}
    res = classify(doc, _dt("resume"), SubtypeResult(), cands, rules)
    assert res.status == "classified" and res.dimension == "person_name"
    assert res.confidence == 0.75
    assert any(e.source == "llm" for e in res.evidence)


def test_tie_review(rules):
    doc = RecognizedDoc(doc_id="c3", text="甲：张三 乙：李四")
    cands = {"person_name": [
        _cand("person_name", "张三", 0.8),
        _cand("person_name", "李四", 0.8),
    ]}
    res = classify(doc, _dt("resume"), SubtypeResult(), cands, rules)
    assert res.status == "review" and res.category_path == ["简历"]


def test_path_with_subtype(rules):
    doc = RecognizedDoc(doc_id="hb", text="业务招待费报销单 报销人：张三 发票 …")
    dt = DocTypeResult(name="reimbursement", confidence=1.0, matched={"reimbursement": 3.0}, status="classified")
    st = SubtypeResult(
        option="hospitality",
        display="业务招待费报销",
        hits={"invoice": MaterialHit(material="invoice", display="发票", section=0, confidence=0.8, keyword="发票")},
    )
    cands = {
        "person_name": [_cand("person_name", "张三", 0.9)],
        "department_name": [],
    }
    res = classify(doc, dt, st, cands, rules)
    assert res.status == "classified" and res.subtype == "hospitality"
    assert res.category_path == ["报销", "业务招待费报销", "张三"]
    assert res.materials == ["invoice"]
