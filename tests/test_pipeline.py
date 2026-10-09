import json
from pathlib import Path

import pytest

from doc_classifier.extractors.llm import LLMExtractor
from doc_classifier.models import RecognizedDoc, Section
from doc_classifier.pipeline import classify_doc, classify_docs
from tests.fakes import FakeClient

FIX = Path(__file__).parent / "fixtures"
BUSINESS = {
    "contract": (["合同", "阿里巴巴（中国）有限公司"], "classified"),
    "resume": (["简历", "张三"], "classified"),
    "purchase_order": (["采购单", "笔记本电脑"], "classified"),
}


def _load(path: str) -> RecognizedDoc:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    raw = d.get("sections") or None
    sections = (
        [Section(index=s.get("index", i), text=s.get("text", ""), title=s.get("title")) for i, s in enumerate(raw)]
        if raw
        else None
    )
    return RecognizedDoc(
        doc_id=d.get("doc_id", ""),
        text=d.get("text", ""),
        sections=sections,
        structured=d.get("structured"),
        source=d.get("source", ""),
    )


@pytest.mark.parametrize("name,args", BUSINESS.items())
def test_business_case(name, args, rules):
    path, status = args
    doc = _load(str(FIX / f"{name}.json"))
    c = classify_doc(doc, rules, llm=None)
    assert c.category_path == path and c.status == status


OFFICE = {
    "meeting_minutes": (["会议纪要", "Q4营销方案评审", "市场部"], "classified"),
    "reimbursement": (["报销"], "review"),  # 单页表单材料不全 → 子类型判不出 → review（design 4.3）
    "leave_request": (["请假单", "李四"], "classified"),
    "invoice": (["发票", "XX信息技术有限公司"], "classified"),
    "notice": (["通知公告", "人力资源部"], "classified"),
    "weekly_report": (["周报/工作总结", "王五"], "classified"),
    "policy": (["规章制度", "行政部"], "classified"),
    "certificate": (["证明材料", "赵文杰"], "classified"),
    "personnel_record": (["人事档案", "张三"], "classified"),
}


@pytest.mark.parametrize("name,args", OFFICE.items())
def test_office_case(name, args, rules):
    path, status = args
    doc = _load(str(FIX / f"{name}.json"))
    c = classify_doc(doc, rules, llm=None)
    assert c.category_path == path and c.status == status, f"{name}: {c}"

CONTRACT = RecognizedDoc(
    doc_id="c1",
    text="技术服务合同 甲方：阿里巴巴（中国）有限公司 乙方：某软件公司 签订日期：2024-01-01",
)

PKG = RecognizedDoc(
    doc_id="pkg",
    text="",
    sections=[
        Section(index=0, text="报销单 报销人：张三 部门：财务部 审批通过"),
        Section(
            index=1,
            text="增值税普通发票 发票号码：1 价税合计：100 购方名称：阿里巴巴（中国）有限公司 税号：91330106MA2XXXXXXX",
        ),
        Section(index=2, text="行程单 登机牌 北京-上海"),
        Section(index=3, text="住宿 酒店 房费 300"),
    ],
)


def test_contract_end_to_end(rules):
    c = classify_doc(CONTRACT, rules, llm=None)
    assert c.status == "classified" and c.doc_type == "contract"
    assert c.category_path == ["合同", "阿里巴巴（中国）有限公司"]
    assert c.subtype is None


def test_reimburse_package_travel(rules):
    c = classify_doc(PKG, rules, llm=None)
    assert c.doc_type == "reimbursement" and c.subtype == "travel_expense"
    assert c.category_path == ["报销", "差旅费报销", "张三"]
    assert set(c.materials) == {"approval", "invoice", "itinerary", "hotel"}


def test_garbage_no_crash(rules):  # 审查重点 #2
    c = classify_doc(RecognizedDoc(doc_id="g", text="###@@@"), rules, llm=None)
    assert c.status == "unknown" and c.category_path == []


def test_llm_not_called_when_rule_hits(rules):
    llm = LLMExtractor(client=None)
    rules.llm.enabled = True
    c = classify_doc(CONTRACT, rules, llm=llm)
    assert llm.calls == 0  # 主维度 party_a 已达标 → 不调用 LLM（次要维度缺失不触发）


def test_llm_fills_below_threshold(rules):
    doc = RecognizedDoc(
        doc_id="r1",
        text="个人简历 他跟李四聊了项目 教育经历",  # 2 字名嵌长 run → 无规则命中
        sections=None,
    )
    llm = LLMExtractor(
        client=FakeClient(reply=json.dumps({"person_name": {"value": "李四", "span": [7, 9], "confidence": 0.8}}))
    )
    rules.llm.enabled = True
    c = classify_doc(doc, rules, llm=llm)
    assert llm.calls == 1 and c.category_path == ["简历", "李四"]


def test_classify_docs_summary(rules):
    docs = [CONTRACT, RecognizedDoc(doc_id="g", text="###@@@"), RecognizedDoc(doc_id="x", text="请假单 请假人：李四 事假")]
    results, summary = classify_docs(docs, rules, llm=None)
    assert summary.total == 3
    assert summary.classified >= 2 and summary.unknown >= 1
    assert summary.llm_docs == 0
