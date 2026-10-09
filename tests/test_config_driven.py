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


def test_dimension_switch_config_only():
    # 同一份合同，改用 person_name 主维度 → 路径随之改变，零代码改动
    rules = load_rules(str(FIX / "rules_alt.yaml"))
    doc = _load(str(FIX / "contract_person.json"))
    c = classify_doc(doc, rules, llm=None)
    assert c.dimension == "person_name" and c.category_path[0] == "合同"
    assert c.category_path[1] != "阿里巴巴（中国）有限公司"
