from doc_classifier.doc_type import detect_doc_type
from doc_classifier.models import RecognizedDoc, Section


def test_keyword_score(rules):
    doc = RecognizedDoc(doc_id="c", text="双方签订合同 甲方：A 乙方：B 合同金额为十万元")
    res = detect_doc_type(doc, rules)
    assert res.name == "contract" and res.status == "classified"


def test_title_boost(rules):
    doc = RecognizedDoc(
        doc_id="m",
        sections=[Section(title="Q4 营销方案评审会议纪要", text="Q4 营销方案评审会议纪要 议题：Q4 营销方案评审")],
    )
    res = detect_doc_type(doc, rules)
    assert res.name == "meeting_minutes" and res.status == "classified"


def test_distinct_keywords(rules):
    doc = RecognizedDoc(doc_id="po", text="采购单：笔记本电脑 供应商：A 甲方：B")
    res = detect_doc_type(doc, rules)
    assert res.name == "purchase_order" and res.status == "classified"


def test_no_section_uses_first_section(rules):
    doc = RecognizedDoc(
        doc_id="r1",
        sections=[
            Section(title=None, text="差旅费报销申请 姓名：张三"),
            Section(title="增值税电子发票", text="项目名称：*信息技术服务* 税额 合同"),
        ],
    )
    res = detect_doc_type(doc, rules)
    assert res.name == "reimbursement" and res.status == "classified"


def test_tie_review(rules):
    doc = RecognizedDoc(doc_id="t", text="关于合同与报销的说明")
    res = detect_doc_type(doc, rules)
    assert res.name is None and res.status == "review" and len(res.matched) >= 2
