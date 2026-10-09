"""抽取器基座：协议 + 上下文（契约见 design 4.3）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ..models import Candidate, MaterialHit, RecognizedDoc


@runtime_checkable
class Extractor(Protocol):
    """抽取器统一契约（规则与 LLM 同构，可替换）。"""

    name: str

    def extract(
        self,
        doc: RecognizedDoc,
        field: str,
        ctx: ExtractContext,
    ) -> list[Candidate]:
        ...


@runtime_checkable
class MaterialDetector(Protocol):
    """材料检测契约（①b；材料定义全部来自 rules.yaml，引擎不硬编码）。"""

    name: str

    def detect(
        self,
        doc: RecognizedDoc,
        material: object,  # MaterialSpec（config 模型，避免循环导入）
        ctx: ExtractContext,
    ) -> list[MaterialHit]:
        ...


@dataclass
class ExtractContext:
    """抽取上下文。`rules`/`dimension` 用字符串注解避免 config ↔ base 循环导入。"""

    rules: "RulesConfig"  # noqa: F821  (doc_classifier.config.RulesConfig)
    dimension: "DimensionSpec | None" = None  # noqa: F821  当前维度规格（labels 等，配置驱动）
    degraded: bool = False  # True = 无分节全文检测（材料检测置信度降档）
