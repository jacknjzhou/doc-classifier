import pytest
from doc_classifier.extractors.base import Extractor
from doc_classifier.extractors.registry import register_extractor, get_extractor


def test_registry_roundtrip():
    class Dummy(Extractor):
        name = "dummy"

        def extract(self, doc, field, ctx):
            return []

    register_extractor("dummy", Dummy())
    assert get_extractor("dummy").name == "dummy"


def test_unregistered_raises():
    with pytest.raises(KeyError):
        get_extractor("no_such_extractor")
