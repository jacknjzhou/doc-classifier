from doc_classifier.normalizers import (
    normalize,
    normalize_item,
    normalize_org,
    normalize_person,
    normalize_topic,
)


def test_normalize_topic_strip():
    assert normalize_topic("关于Q4营销方案评审的会议纪要") == normalize_topic("Q4营销方案评审")


def test_dispatch_topic():
    assert normalize("关于X的会议纪要", "topic") == normalize_topic("关于X的会议纪要")


def test_org_suffix_strip():
    assert normalize_org("阿里巴巴（中国）有限公司") == "阿里巴巴"


def test_org_branch_strip():
    assert normalize_org("华为技术有限公司上海分公司") == "华为技术有限公司"


def test_person_strip_honorific():
    assert normalize_person("张经理") == "张"
    assert normalize_person("李四") == "李四"


def test_topic_from_title():
    assert normalize_topic("Q4 营销方案评审会议纪要") == "Q4 营销方案评审"
    assert normalize_topic("季度工作总结报告") == "季度"
    assert normalize_topic("年度总结") == "年度总结"  # 过短不裁


def test_item_strip_spec_and_qty():
    assert normalize_item("联想笔记本电脑 14寸 i7/16G") == "联想笔记本电脑"
    assert normalize_item("打印纸 A4 500张") == "打印纸"


def test_dispatch(rules):
    assert normalize("某某科技有限公司", "party_a_name", rules) == "某某"
    assert normalize("李四", "person_name", rules) == "李四"
    assert normalize("笔记本电脑", "item_name", rules) == "笔记本电脑"
