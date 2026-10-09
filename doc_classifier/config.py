"""rules.yaml 加载与校验（pydantic 全量 schema，见 design 4.4）。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from .extractors.registry import get_material_detector


class DimensionSpec(BaseModel):
    extractor: str
    normalize: str
    llm_fallback: bool = False
    threshold: float = 0.6
    labels: list[str] = Field(default_factory=list)


class DetectSpec(BaseModel):
    keywords: list[str]
    min_score: int = 1


class DimensionRef(BaseModel):
    use: str
    priority: int


class MaterialSpec(BaseModel):
    display: str
    keywords: list[str]
    detector: str | None = None  # 自定义检测器注册名；默认 "keyword"
    name: str = ""  # 材料名（= yaml 键；load 时回填，供检测器使用）


class SubtypeOption(BaseModel):
    display: str
    required: list[str]
    optional: list[str] = Field(default_factory=list)
    weight_required: float = 2.0
    weight_optional: float = 1.0
    dimensions: list[DimensionRef] = Field(default_factory=list)  # 维度覆盖


class SubtypesSpec(BaseModel):
    materials: dict[str, MaterialSpec]
    options: dict[str, SubtypeOption]


class DocTypeSpec(BaseModel):
    display: str
    detect: DetectSpec
    dimensions: list[DimensionRef]
    subtypes: SubtypesSpec | None = None  # 无此段 = 不启用子类型层（零开销）


class LLMConfig(BaseModel):
    enabled: bool = False  # 主开关默认关闭
    base_url: str = ""
    api_key_env: str = "OPENAI_API_KEY"
    model: str = ""
    timeout_sec: float = 20.0
    max_retries: int = 2


class RulesConfig(BaseModel):
    version: str
    llm: LLMConfig = Field(default_factory=LLMConfig)
    dimensions: dict[str, DimensionSpec]
    document_types: dict[str, DocTypeSpec]

    @model_validator(mode="after")
    def _cross_validate(self) -> "RulesConfig":
        for key, dt in self.document_types.items():
            for ref in dt.dimensions:
                if ref.use not in self.dimensions:
                    raise ValueError(
                        f"document_types.{key}: undefined dimension ref '{ref.use}'"
                    )
            st = dt.subtypes
            if st is None:
                continue
            for mname, mat in st.materials.items():
                mat.name = mname  # 回填材料名（yaml 键）供检测器使用
                if not mat.keywords:
                    raise ValueError(
                        f"document_types.{key}.subtypes.materials.{mname}: keywords must be non-empty"
                    )
                if mat.detector:
                    try:
                        get_material_detector(mat.detector)
                    except KeyError:
                        raise ValueError(
                            f"document_types.{key}.subtypes.materials.{mname}: "
                            f"unregistered detector '{mat.detector}'"
                        ) from None
            for oname, opt in st.options.items():
                if not opt.required:
                    raise ValueError(
                        f"document_types.{key}.subtypes.options.{oname}: at least one required material"
                    )
                for m in [*opt.required, *opt.optional]:
                    if m not in st.materials:
                        raise ValueError(
                            f"document_types.{key}.subtypes.options.{oname}: undefined material '{m}'"
                        )
        return self


def load_rules(path: str | Path) -> RulesConfig:
    """读 YAML → schema 校验 → 交叉校验；非法配置抛 ValidationError（含 offending 键名）。"""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return RulesConfig.model_validate(data)
