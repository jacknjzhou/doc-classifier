from pathlib import Path

from doc_classifier.config import load_rules

RULES = Path(__file__).resolve().parent.parent / "doc_classifier" / "rules.yaml"


def test_rules_yaml_loads():
    rules = load_rules(str(RULES))
    assert len(rules.document_types) == 12
    assert len(rules.dimensions) == 6
    assert "travel_expense" in rules.document_types["reimbursement"].subtypes.options
    assert rules.dimensions["person_name"].labels == ["姓名", "报销人", "请假人", "申请人", "联系人", "作者"]
    assert rules.llm.enabled is False
    assert rules.version == "1.3"
