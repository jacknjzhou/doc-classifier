"""数据模型（最终形态，见 design 4.3）。

注意：本模块字段一次性定义到位，后续任务不得再改字段——避免回退式扩展。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Section:
    index: int  # 分节/页序号（0 起）
    text: str


@dataclass
class RecognizedDoc:
    doc_id: str
    text: str  # 全文（各分节拼接）
    sections: list[Section] | None = None  # 页/分节结构；None = 无分节信息，按全文处理
    structured: dict[str, Any] | None = None
    source: str = ""


@dataclass
class Candidate:
    value: str  # 原始命中值
    field: str  # 目标维度名（party_a_name / person_name / item_name / department_name / meeting_name / invoice_title）
    confidence: float  # 0~1
    source: str  # "rule" | "llm"
    span: tuple[int, int] | None = None  # 证据在全文中的位置


@dataclass
class MaterialHit:
    material: str  # materials 定义中的材料名（如 "invoice"）
    display: str  # 显示名（如 "发票"）
    section: int | None  # 命中分节；None = 全文检测（无分节信息时的降级）
    confidence: float
    keyword: str  # 命中的关键词（证据）
    degraded: bool = False  # 全文降级检测标记


@dataclass
class Evidence:
    source: str  # "rule" | "llm" | "material" | "doc_type"
    value: str  # 命中值 / 关键词
    span: tuple[int, int] | None
    confidence: float


@dataclass
class SubtypeResult:
    option: str | None = None  # 命中的 option key；无候选/并列时 None
    display: str | None = None  # 命中 option 的显示名
    tie: bool = False  # 最高分并列标记
    hits: dict[str, MaterialHit] = field(default_factory=dict)  # 材料名 → 最高命中


@dataclass
class Classification:
    doc_id: str
    doc_type: str | None = None  # 文档类型 key；无法判定时 None
    subtype: str | None = None  # 子类型 key（报销类型）；未启用或无命中为 None
    dimension: str | None = None  # 实际采用的主维度
    category_key: str | None = None  # 主维度归一化键（扁平，用于分组/建目录）
    category_display: str | None = None  # 主维度展示名
    category_path: list[str] = field(default_factory=list)  # 层级归档路径
    materials: list[str] = field(default_factory=list)  # 命中的材料名（证据）
    confidence: float = 0.0
    evidence: list[Evidence] = field(default_factory=list)
    status: str = "unknown"  # "classified" | "review" | "unknown"
