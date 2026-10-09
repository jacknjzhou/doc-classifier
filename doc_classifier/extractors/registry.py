"""抽取器/材料检测器注册表（按名字取用，供 rules.yaml 引用）。"""

from __future__ import annotations

from .base import Extractor, MaterialDetector

_EXTRACTORS: dict[str, Extractor] = {}
_DETECORS: dict[str, MaterialDetector] = {}


def register_extractor(name: str, ex: Extractor) -> None:
    _EXTRACTORS[name] = ex


def get_extractor(name: str) -> Extractor:
    try:
        return _EXTRACTORS[name]
    except KeyError:
        raise KeyError(f"unregistered extractor: {name}") from None


def register_material_detector(name: str, det: MaterialDetector) -> None:
    _DETECORS[name] = det


def get_material_detector(name: str) -> MaterialDetector:
    try:
        return _DETECORS[name]
    except KeyError:
        raise KeyError(f"unregistered material detector: {name}") from None
