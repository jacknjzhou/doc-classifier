from pathlib import Path

import pytest

from doc_classifier import config
from doc_classifier.config import load_rules
from doc_classifier.extractors.base import ExtractContext


def _package_rules() -> Path:
    return Path(config.__file__).resolve().parent / "rules.yaml"


@pytest.fixture
def rules():
    return load_rules(str(_package_rules()))


@pytest.fixture
def ctx(rules):
    return ExtractContext(rules=rules)
