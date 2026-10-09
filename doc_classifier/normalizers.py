"""③ 归一化：维度值归一化（配置分派 + 内置默认，design 4.6）。

normalize 名由 rules.yaml 的 DimensionSpec.normalize 决定（org/person/item/topic/invoice_title）；
空串 = 恒等。新增归一化策略 = 在此注册 + 配置引用，不改流水线代码。
"""

from __future__ import annotations

import re

from .config import RulesConfig

# 机构后缀：先摘"分公司"类，再循环摘后缀（长词优先）
_BRANCH = re.compile(r"(分公司|分部|分支机构)$")
_ORG_SUFFIXES = sorted(
    [
        "有限责任公司", "股份有限公司", "集团有限公司", "有限公司", "公司",
        "研究院", "研究所", "研究中心", "办事处", "中心", "集团",
        "大学", "学院", "学校", "医院", "银行",
        "科技", "信息", "网络", "技术", "电子", "软件", "通信",
        "实业", "贸易", "咨询", "服务", "教育", "文化", "传媒",
        "工程", "建筑", "机械", "医药", "生物",
    ],
    key=len,
    reverse=True,
)
_PAREN = re.compile(r"[（(][^（）()]*[）)]$")

_HONORIFICS = sorted(
    ["先生", "女士", "同志", "经理", "总监", "主管", "部长", "科长", "主任", "老师"],
    key=len,
    reverse=True,
)

_TOPIC_SUFFIXES = sorted(
    [
        "会议纪要", "会议记录", "纪要", "记录", "决议", "通知", "通报",
        "报告", "总结", "请示", "批复", "函", "备忘录", "协议", "合同",
        "说明书", "清单", "明细", "附录", "附件",
    ],
    key=len,
    reverse=True,
)

_QTY = re.compile(r"\d{1,4}\s*(?:张|个|台|套|件|箱|盒|包|桶|本|册)$")
_SPEC_TAIL = re.compile(r"\s+(?:\d|寸|英寸|[A-Za-z]).*$")


def normalize_org(value: str) -> str:
    v = value.strip()
    if _BRANCH.search(v):  # "…公司上海分公司" → 截到最后一个"公司"（不再走后缀循环，避免把本体裁掉）
        idx = v.rfind("公司")
        if idx >= 0:
            return v[: idx + 2]
        cut = _BRANCH.sub("", v)
        return cut if cut else value
    changed = True
    while changed:
        changed = False
        for s in _ORG_SUFFIXES:
            if v.endswith(s) and len(v) - len(s) >= 2:
                v = v[: -len(s)]
                changed = True
                break
        if _PAREN.search(v) and len(v) - len(_PAREN.search(v).group(0)) >= 2:
            v = _PAREN.sub("", v)
            changed = True
    return v or value


def normalize_person(value: str) -> str:
    v = value.strip()
    changed = True
    while changed:
        changed = False
        for h in _HONORIFICS:
            if v.endswith(h) and len(v) - len(h) >= 1:
                v = v[: -len(h)]
                changed = True
                break
    return v or value


def normalize_item(value: str) -> str:
    v = value.strip()
    v = _QTY.sub("", v)  # 尾部数量（"打印纸 A4 500张" → "打印纸 A4"）
    v = re.sub(r"\s+$", "", v)
    v = _SPEC_TAIL.sub("", v)  # 规格/型号尾段（首个空格后为数字/英寸/字母 → 整段裁掉）
    v = _QTY.sub("", v)
    v = v.strip()
    return v if len(v) >= 2 else value


def normalize_topic(value: str) -> str:
    """标题 → 议题：循环裁尾部公文后缀，保留至少 4 字。"""
    v = value.strip()
    changed = True
    while changed:
        changed = False
        for s in _TOPIC_SUFFIXES:
            if v.endswith(s) and len(v) - len(s) >= 4:
                v = v[: -len(s)]
                changed = True
                break
    return v or value


def normalize_invoice_title(value: str) -> str:
    """发票货物名称：去 *类目* 前缀 / 尾部税率括号 / "发票" 尾字。"""
    v = value.strip()
    v = re.sub(r"^\*[^*]*\*", "", v)
    v = re.sub(r"[（(][^（）()]*%[）)]\s*$", "", v)
    v = re.sub(r"发票$", "", v)
    v = v.strip()
    return v if v else value


_NORMALIZERS = {
    "org": normalize_org,
    "person": normalize_person,
    "item": normalize_item,
    "topic": normalize_topic,
    "invoice_title": normalize_invoice_title,
}


def normalize(value: str, dim_name: str, rules: RulesConfig) -> str:
    """按维度配置的 normalize 名分派（未配置/未知名 = 恒等）。"""
    dim = rules.dimensions.get(dim_name)
    if dim is None or not dim.normalize:
        return value
    fn = _NORMALIZERS.get(dim.normalize)
    if fn is None:
        return value
    return fn(value) or value
