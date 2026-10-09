from doc_classifier.config import load_rules
from doc_classifier.pipeline import classify_doc
from tests.util import FIX, _load


def test_telecom_expense_config_only():
    # 不改任何引擎代码：扩展 YAML 新增材料 telecom_bill + 报销类型 telecom_expense
    rules = load_rules(str(FIX / "rules_reimburse_ext.yaml"))
    doc = _load(str(FIX / "reimburse_telecom.json"))
    c = classify_doc(doc, rules, llm=None)
    assert c.subtype == "telecom_expense"
    assert c.category_path == ["报销", "通讯费报销", "张三"]
