from doc_classifier.config import MaterialSpec, SubtypeOption, SubtypesSpec
from doc_classifier.models import MaterialHit
from doc_classifier.subtype import resolve_subtype


def _hit(name, display, conf=0.7):
    return MaterialHit(material=name, display=display, section=0, confidence=conf, keyword="x")


def _specs():  # 与 rules.yaml 报销一致的 option 结构
    return SubtypesSpec(
        materials={
            m: MaterialSpec(display=m, keywords=[m])
            for m in ["invoice", "itinerary", "hotel", "taxi", "meal", "approval"]
        },
        options={
            "travel_expense": SubtypeOption(
                display="差旅费报销", required=["invoice", "itinerary"], optional=["hotel", "taxi"]
            ),
            "hospitality": SubtypeOption(display="业务招待费报销", required=["invoice", "meal", "approval"]),
            "office_supplies": SubtypeOption(display="办公用品报销", required=["invoice", "approval"]),
        },
    )


def _resolve(hit_names, display=None, specs=None):
    hits = {n: _hit(n, display or n) for n in hit_names}
    return resolve_subtype(hits, specs or _specs())


def test_travel():
    r = _resolve(["invoice", "itinerary", "hotel"])
    assert r.option == "travel_expense" and r.tie is False


def test_hospitality():
    r = _resolve(["invoice", "meal", "approval"])
    assert r.option == "hospitality"  # 6 > office 4


def test_incomplete_none():
    r = _resolve(["invoice"])
    assert r.option is None and r.tie is False  # required 不全 → 无候选


def test_tie():
    spec = SubtypesSpec(
        materials={
            "a": MaterialSpec(display="A", keywords=["a"]),
            "b": MaterialSpec(display="B", keywords=["b"]),
        },
        options={
            "o1": SubtypeOption(display="O1", required=["a"]),
            "o2": SubtypeOption(display="O2", required=["a"]),
        },
    )
    r = resolve_subtype({"a": _hit("a", "A")}, spec)
    assert r.option is None and r.tie is True  # 并列 → 不猜


def test_weights_configurable():
    spec = SubtypesSpec(
        materials={
            "a": MaterialSpec(display="A", keywords=["a"]),
            "b": MaterialSpec(display="B", keywords=["b"]),
        },
        options={"o1": SubtypeOption(display="O1", required=["a"], optional=["b"], weight_optional=5.0)},
    )
    r = resolve_subtype({"a": _hit("a", "A"), "b": _hit("b", "B")}, spec)
    assert r.option == "o1"  # 2 + 5×1 = 7（optional 权重生效）
