import json

import pytest

from doc_classifier.extractors.base import ExtractContext
from doc_classifier.extractors.llm import LLMExtractor
from doc_classifier.models import RecognizedDoc

VALID = json.dumps({"person_name": {"value": "张三", "span": [3, 5], "confidence": 0.8}})


class FakeClient:
    def __init__(self, reply=VALID, fail=False):
        self.reply = reply
        self.fail = fail
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if self.fail:
            raise TimeoutError("boom")
        class R:
            content = self.reply
        return R()


def _llm(rules, client, enabled):
    rules.llm.enabled = enabled
    return LLMExtractor(client=client)


def test_disabled_no_call(rules):
    c = FakeClient()
    llm = _llm(rules, c, enabled=False)
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    assert llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules)) == {"person_name": []}
    assert c.calls == 0


def test_env_off_wins(rules, monkeypatch):
    monkeypatch.setenv("DOC_CLASSIFIER_LLM", "off")
    c = FakeClient()
    llm = _llm(rules, c, enabled=True)
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    assert llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))["person_name"] == []
    assert c.calls == 0


def test_valid_json(rules):
    c = FakeClient()
    llm = _llm(rules, c, enabled=True)
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    out = llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))
    assert out["person_name"][0].value == "张三" and out["person_name"][0].source == "llm"
    assert out["person_name"][0].confidence == 0.8


def test_bad_json_degrades(rules):
    c = FakeClient(reply="这不是JSON", fail=False)
    llm = _llm(rules, c, enabled=True)
    rules.llm.max_retries = 2
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    out = llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))
    assert out["person_name"] == [] and llm.failed >= 1  # 重试耗尽→降级，不抛异常


def test_cache_avoids_second_call(rules):
    c = FakeClient()
    llm = _llm(rules, c, enabled=True)
    doc = RecognizedDoc(doc_id="x", text="姓名：张三")
    llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))
    llm.extract_fields(doc, ["person_name"], ExtractContext(rules=rules))
    assert c.calls == 1
