from doc_classifier.pipeline import classify_docs
from tests.util import FIX, _load

ALL = [
    "contract", "resume", "purchase_order", "meeting_minutes", "reimbursement",
    "leave_request", "invoice", "notice", "weekly_report", "policy", "certificate",
    "personnel_record",
]


def test_batch_metrics(rules):
    docs = [_load(str(FIX / f"{n}.json")) for n in ALL]
    results, summary = classify_docs(docs, rules, llm=None)
    assert summary.total == 12
    assert summary.classified == 11 and summary.review == 1  # reimbursement 单页 → review
    assert summary.llm_docs == 0 and summary.rule_hit_rate == 1.0  # 成功标准 #1：规则命中率 ≥ 0.7
    assert summary.llm_rate == 0.0  # 成功标准 #2：LLM 调用率 ≤ 0.3
    assert all(r.evidence for r in results if r.status == "classified")  # 成功标准 #3：证据可追溯
